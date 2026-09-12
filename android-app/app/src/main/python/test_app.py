#!/usr/bin/env python3
"""
测试Flask应用的简单脚本
用于验证Python代码的正确性
"""

import sys
import os

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """测试必要的模块导入"""
    try:
        from flask import Flask, jsonify, request
        import sqlite3
        from datetime import datetime
        import re
        print("[OK] 所有模块导入成功")
        return True
    except ImportError as e:
        print(f"[ERROR] 模块导入失败: {e}")
        return False

def test_database_helper():
    """测试数据库助手"""
    try:
        from database_helper import copy_database_from_assets, check_database_integrity
        print("[OK] 数据库助手模块导入成功")
        return True
    except ImportError as e:
        print(f"[ERROR] 数据库助手导入失败: {e}")
        return False

def test_app_structure():
    """测试应用结构"""
    try:
        import app
        print("[OK] Flask应用模块导入成功")
        
        # 检查必要的路由
        routes = [rule.rule for rule in app.app.url_map.iter_rules()]
        required_routes = ['/api/search/<word>', '/api/autocomplete', '/api/wordbook', '/api/review']
        
        for route in required_routes:
            if route in routes:
                print(f"[OK] 路由 {route} 存在")
            else:
                print(f"[ERROR] 路由 {route} 不存在")
                return False
        
        return True
    except Exception as e:
        print(f"[ERROR] Flask应用测试失败: {e}")
        return False

def test_database_file():
    """测试数据库文件"""
    db_files = ['简明英汉字典增强版.db']
    for db_file in db_files:
        if os.path.exists(db_file):
            print(f"[OK] 数据库文件 {db_file} 存在")
        else:
            print(f"[ERROR] 数据库文件 {db_file} 不存在")
            return False
    return True

def main():
    """主测试函数"""
    print("开始测试Python应用...")
    print("=" * 50)
    
    tests = [
        ("模块导入", test_imports),
        ("数据库助手", test_database_helper),
        ("应用结构", test_app_structure),
        ("数据库文件", test_database_file)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n测试 {test_name}...")
        if test_func():
            passed += 1
        else:
            print(f"测试 {test_name} 失败")
    
    print("=" * 50)
    print(f"测试结果: {passed}/{total} 通过")
    
    if passed == total:
        print("[SUCCESS] 所有测试通过！应用可以正常运行")
        return True
    else:
        print("[ERROR] 部分测试失败，请检查上述错误信息")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)