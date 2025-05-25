# database_syncer.py
import os
import json
import threading
import time
import hashlib
import queue
from datetime import datetime
from typing import Dict, Optional, Any, List
import pymongo
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
import traceback

# --- Configuration ---
MONGODB_URI_ENV_VAR = "MONGODB_CONNECTION_STRING"
DATABASE_NAME = "fudan_agent"
COLLECTION_NAME = "files"

# Thread-safe queue for async uploads
upload_queue = queue.Queue()
_sync_thread = None
_stop_sync = threading.Event()

class DatabaseSyncer:
    def __init__(self):
        self.client: Optional[MongoClient] = None
        self.db = None
        self.collection = None
        self.connected = False
        self.base_data_dir = "data"
        self._init_connection()
    
    def _init_connection(self):
        """Initialize MongoDB connection using environment variable."""
        connection_string = os.getenv(MONGODB_URI_ENV_VAR)
        if not connection_string:
            print(f"警告: 环境变量 {MONGODB_URI_ENV_VAR} 未设置。MongoDB 同步功能将被禁用。")
            return
        
        try:
            self.client = MongoClient(connection_string, serverSelectionTimeoutMS=5000)
            # Test connection
            self.client.admin.command('ping')
            self.db = self.client[DATABASE_NAME]
            self.collection = self.db[COLLECTION_NAME]
            self.connected = True
            print("✅ MongoDB 连接成功建立。")
            
            # Create indexes for better performance
            self.collection.create_index("file_path", unique=True)
            self.collection.create_index("last_modified")
            
        except ConnectionFailure as e:
            print(f"❌ MongoDB 连接失败: {e}")
            self.connected = False
        except Exception as e:
            print(f"❌ MongoDB 初始化错误: {e}")
            self.connected = False
    
    def _get_file_metadata(self, file_path: str) -> Optional[Dict]:
        """Get file metadata including modification time and content hash."""
        if not os.path.exists(file_path):
            return None
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            stat = os.stat(file_path)
            content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
            
            return {
                "content": content,
                "last_modified": datetime.fromtimestamp(stat.st_mtime),
                "checksum": content_hash,
                "size": stat.st_size
            }
        except Exception as e:
            print(f"读取文件元数据失败 {file_path}: {e}")
            return None
    
    def _normalize_path(self, file_path: str) -> str:
        """Normalize file path to use forward slashes and be relative to data directory."""
        # Convert to relative path if it's absolute
        if os.path.isabs(file_path):
            try:
                file_path = os.path.relpath(file_path, os.getcwd())
            except ValueError:
                pass  # Keep as is if can't make relative
        
        # Normalize path separators
        return file_path.replace('\\', '/')
    
    def upload_file_to_mongodb(self, file_path: str) -> bool:
        """Upload a single file to MongoDB."""
        if not self.connected:
            return False
        
        try:
            metadata = self._get_file_metadata(file_path)
            if not metadata:
                print(f"无法读取文件元数据: {file_path}")
                return False
            
            normalized_path = self._normalize_path(file_path)
            
            # Parse JSON content
            try:
                json_content = json.loads(metadata["content"])
            except json.JSONDecodeError as e:
                print(f"文件不是有效的JSON格式 {file_path}: {e}")
                return False
            
            document = {
                "file_path": normalized_path,
                "content": json_content,
                "last_modified": metadata["last_modified"],
                "checksum": metadata["checksum"],
                "size": metadata["size"],
                "upload_timestamp": datetime.now()
            }
            
            # Use upsert to insert or update
            result = self.collection.replace_one(
                {"file_path": normalized_path},
                document,
                upsert=True
            )
            
            if result.upserted_id or result.modified_count > 0:
                print(f"✅ 文件已上传到MongoDB: {normalized_path}")
                return True
            else:
                print(f"⚠️ 文件上传到MongoDB无变化: {normalized_path}")
                return True
                
        except Exception as e:
            print(f"❌ 上传文件到MongoDB失败 {file_path}: {e}")
            traceback.print_exc()
            return False
    
    def download_file_from_mongodb(self, file_path: str, force_overwrite: bool = False) -> bool:
        """Download a single file from MongoDB to local storage."""
        if not self.connected:
            return False
        
        try:
            normalized_path = self._normalize_path(file_path)
            document = self.collection.find_one({"file_path": normalized_path})
            
            if not document:
                print(f"MongoDB中未找到文件: {normalized_path}")
                return False
            
            # Check if local file exists and compare timestamps
            if os.path.exists(file_path) and not force_overwrite:
                local_metadata = self._get_file_metadata(file_path)
                if local_metadata:
                    local_modified = local_metadata["last_modified"]
                    remote_modified = document["last_modified"]
                    
                    if local_modified >= remote_modified:
                        print(f"⏭️ 本地文件较新，跳过下载: {file_path}")
                        return True
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Write content to file
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(document["content"], f, ensure_ascii=False, indent=4)
            
            # Set file modification time to match MongoDB
            if "last_modified" in document:
                mod_time = document["last_modified"].timestamp()
                os.utime(file_path, (mod_time, mod_time))
            
            print(f"✅ 文件已从MongoDB下载: {file_path}")
            return True
            
        except Exception as e:
            print(f"❌ 从MongoDB下载文件失败 {file_path}: {e}")
            traceback.print_exc()
            return False
    
    def get_all_remote_files(self) -> List[Dict]:
        """Get list of all files in MongoDB."""
        if not self.connected:
            return []
        
        try:
            return list(self.collection.find({}, {"file_path": 1, "last_modified": 1, "checksum": 1}))
        except Exception as e:
            print(f"❌ 获取MongoDB文件列表失败: {e}")
            return []
    
    def get_all_local_files(self) -> List[str]:
        """Get list of all JSON files in the data directory."""
        local_files = []
        
        if not os.path.exists(self.base_data_dir):
            return local_files
        
        for root, dirs, files in os.walk(self.base_data_dir):
            for file in files:
                if file.endswith('.json'):
                    file_path = os.path.join(root, file)
                    local_files.append(file_path)
        
        return local_files
    
    def sync_initial_data(self):
        """Perform initial two-way sync between local files and MongoDB."""
        if not self.connected:
            print("⚠️ MongoDB未连接，跳过初始同步。")
            return
        
        print("🔄 开始初始数据同步...")
        
        # Get all local and remote files
        local_files = self.get_all_local_files()
        remote_files = self.get_all_remote_files()
        
        # Create sets for easier comparison
        local_paths = set(self._normalize_path(f) for f in local_files)
        remote_paths = set(f["file_path"] for f in remote_files)
        
        # Create lookup for remote file metadata
        remote_metadata = {f["file_path"]: f for f in remote_files}
        
        uploaded_count = 0
        downloaded_count = 0
        
        # Upload files that exist locally but not remotely
        for local_file in local_files:
            normalized = self._normalize_path(local_file)
            if normalized not in remote_paths:
                if self.upload_file_to_mongodb(local_file):
                    uploaded_count += 1
        
        # Download files that exist remotely but not locally
        for remote_path in remote_paths:
            if remote_path not in local_paths:
                # Convert normalized path back to local path
                local_path = remote_path.replace('/', os.sep)
                if self.download_file_from_mongodb(local_path):
                    downloaded_count += 1
        
        # Compare and sync files that exist in both places
        conflict_resolved = 0
        for local_file in local_files:
            normalized = self._normalize_path(local_file)
            if normalized in remote_metadata:
                local_metadata = self._get_file_metadata(local_file)
                remote_meta = remote_metadata[normalized]
                
                if local_metadata and local_metadata["checksum"] != remote_meta["checksum"]:
                    # Files are different, compare timestamps
                    local_modified = local_metadata["last_modified"]
                    remote_modified = remote_meta["last_modified"]
                    
                    if local_modified > remote_modified:
                        # Local is newer, upload to MongoDB
                        if self.upload_file_to_mongodb(local_file):
                            print(f"🔄 本地文件较新，已上传: {normalized}")
                            conflict_resolved += 1
                    elif remote_modified > local_modified:
                        # Remote is newer, download from MongoDB
                        if self.download_file_from_mongodb(local_file, force_overwrite=True):
                            print(f"🔄 远程文件较新，已下载: {normalized}")
                            conflict_resolved += 1
        
        print(f"✅ 初始同步完成: 上传 {uploaded_count} 个文件, 下载 {downloaded_count} 个文件, 解决冲突 {conflict_resolved} 个")

# Global syncer instance
_syncer_instance: Optional[DatabaseSyncer] = None

def get_syncer() -> DatabaseSyncer:
    """Get or create the global syncer instance."""
    global _syncer_instance
    if _syncer_instance is None:
        _syncer_instance = DatabaseSyncer()
    return _syncer_instance

def async_upload_worker():
    """Background worker to process upload queue."""
    syncer = get_syncer()
    
    while not _stop_sync.is_set():
        try:
            # Get item from queue with timeout
            file_path = upload_queue.get(timeout=1.0)
            
            if file_path is None:  # Poison pill to stop worker
                break
            
            # Upload file
            syncer.upload_file_to_mongodb(file_path)
            upload_queue.task_done()
            
        except queue.Empty:
            continue
        except Exception as e:
            print(f"❌ 异步上传工作线程错误: {e}")
            traceback.print_exc()

def start_async_sync():
    """Start the background sync worker thread."""
    global _sync_thread
    if _sync_thread is None or not _sync_thread.is_alive():
        _stop_sync.clear()
        _sync_thread = threading.Thread(target=async_upload_worker, daemon=True)
        _sync_thread.start()
        print("🚀 异步同步工作线程已启动。")

def stop_async_sync():
    """Stop the background sync worker thread."""
    global _sync_thread
    _stop_sync.set()
    
    # Add poison pill to queue
    upload_queue.put(None)
    
    if _sync_thread and _sync_thread.is_alive():
        _sync_thread.join(timeout=5.0)
        print("🛑 异步同步工作线程已停止。")

def queue_file_for_upload(file_path: str):
    """Queue a file for asynchronous upload to MongoDB."""
    if get_syncer().connected:
        upload_queue.put(file_path)
        print(f"📤 文件已加入上传队列: {file_path}")

def sync_file_immediately(file_path: str) -> bool:
    """Immediately sync a file to MongoDB (blocking operation)."""
    return get_syncer().upload_file_to_mongodb(file_path)

# Wrapper functions for existing knowledge_base functions
def enhanced_save_json_file(file_path: str, data, sync_to_db: bool = True) -> bool:
    """Enhanced version of _save_json_file that also syncs to MongoDB."""
    try:
        # Ensure directory exists
        parent_dir = os.path.dirname(file_path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)
        
        # Save file locally
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        
        # Queue for MongoDB upload if enabled
        if sync_to_db:
            queue_file_for_upload(file_path)
        
        return True
        
    except Exception as e:
        print(f"❌ 保存文件失败 {file_path}: {e}")
        return False

# Initialize sync system
def initialize_database_sync():
    """Initialize the database sync system."""
    syncer = get_syncer()
    
    if syncer.connected:
        print("🔄 开始数据库同步初始化...")
        syncer.sync_initial_data()
        start_async_sync()
        print("✅ 数据库同步系统已初始化。")
    else:
        print("⚠️ MongoDB连接失败，数据库同步功能已禁用。")

# Cleanup function
def cleanup_database_sync():
    """Cleanup database sync resources."""
    stop_async_sync()
    
    syncer = get_syncer()
    if syncer.client:
        syncer.client.close()
        print("📴 MongoDB连接已关闭。") 