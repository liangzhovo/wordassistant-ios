import os
import shutil
import sqlite3

def copy_database_from_assets():
    """从assets目录复制数据库到应用目录"""
    # Android应用中的数据库路径
    db_path = "/data/data/com.example.wordassistant/databases/简明英汉字典增强版.db"
    assets_db = "简明英汉字典增强版.db"
    
    # 确保目录存在
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    # 如果数据库不存在，从assets复制
    if not os.path.exists(db_path):
        try:
            # 在Android环境中，我们可以通过Java代码访问assets
            # 这里先尝试直接复制，如果失败则通过Java代码处理
            if os.path.exists(assets_db):
                shutil.copy2(assets_db, db_path)
                print(f"数据库已从 {assets_db} 复制到 {db_path}")
            else:
                print(f"警告: assets数据库文件 {assets_db} 不存在")
        except Exception as e:
            print(f"数据库复制失败: {e}")
    
    return db_path

def check_database_integrity(db_path):
    """检查数据库完整性"""
    if not os.path.exists(db_path):
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 检查必要的表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mdx'")
        if cursor.fetchone() is None:
            print("警告: mdx表不存在")
            return False
            
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_words'")
        if cursor.fetchone() is None:
            print("警告: user_words表不存在")
            return False
            
        conn.close()
        return True
    except Exception as e:
        print(f"数据库完整性检查失败: {e}")
        return False

if __name__ == "__main__":
    db_path = copy_database_from_assets()
    if db_path:
        print(f"数据库路径: {db_path}")
        if check_database_integrity(db_path):
            print("数据库完整性检查通过")
        else:
            print("数据库完整性检查失败")
    else:
        print("数据库复制失败")