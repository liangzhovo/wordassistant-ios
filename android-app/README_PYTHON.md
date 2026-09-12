# 单词助手 Android APK (Python版本)

这是一个基于WebView的单词助手Android应用，使用Chaquopy在Android应用中嵌入Python解释器，保持原有的Flask后端架构。

## 🚀 项目特色

- ✅ **保持Python架构**: 使用原有的Flask后端，无需重写
- ✅ **完整功能**: 所有单词助手功能完整保留
- ✅ **离线使用**: 数据库内置，无需网络连接
- ✅ **高性能**: Python直接运行，无网络通信开销
- ✅ **易于维护**: Python代码保持不变，只需小幅度修改

## 📁 项目结构

```
android-app/
├── app/
│   ├── src/
│   │   ├── main/
│   │   │   ├── java/
│   │   │   │   └── com/
│   │   │   │       └── example/
│   │   │   │           └── wordassistant/
│   │   │   │               └── MainActivity.kt      # 主Activity
│   │   │   ├── python/                                # Python代码
│   │   │   │   ├── app.py                             # Flask应用
│   │   │   │   ├── database_helper.py                # 数据库助手
│   │   │   │   └── __init__.py                       # Python包初始化
│   │   │   ├── assets/
│   │   │   │   ├── index.html                        # 前端界面
│   │   │   │   ├── 简明英汉字典增强版.db              # 数据库文件
│   │   │   │   └── database_setup.py                 # 数据库设置脚本
│   │   │   ├── AndroidManifest.xml
│   │   │   └── res/
│   │   └── build.gradle
│   └── build.gradle
├── build.gradle
├── settings.gradle
├── gradle.properties
├── BUILD_PYTHON_APK.bat                              # 构建脚本
└── BUILD_INSTRUCTIONS_PYTHON.md                      # 详细构建说明
```

## 🔧 技术实现

### 核心组件

1. **MainActivity.kt**
   - 初始化Python环境 (Chaquopy)
   - 启动Flask服务器
   - 管理WebView和JavaScript接口

2. **app.py**
   - 原有的Flask应用
   - 提供所有API端点
   - 处理SQLite数据库操作

3. **database_helper.py**
   - 处理数据库文件复制
   - 检查数据库完整性

4. **index.html**
   - 前端界面
   - 通过WebView加载
   - JavaScript与Python后端通信

### 架构优势

```
WebView (Android)
    ↓ (HTTP请求)
Flask Server (Python)
    ↓ (SQLite)
Database (SQLite)
```

## 📱 构建步骤

### 方法1: 使用构建脚本 (推荐)

```bash
# 运行构建脚本
BUILD_PYTHON_APK.bat
```

### 方法2: 使用Android Studio

1. **打开项目**
   - 启动Android Studio
   - 选择 "Open an existing Android Studio project"
   - 选择 `android-app` 目录

2. **同步项目**
   - 等待项目同步完成
   - 点击 "Sync Now"（如果需要）

3. **构建APK**
   - 点击 "Build" → "Build Bundle(s) / APK(s)" → "Build APK(s)"
   - 等待构建完成

4. **安装测试**
   - 连接Android设备或启动模拟器
   - 点击 "Run" → "Run 'app'"
   - 或手动安装：`adb install app/build/outputs/apk/debug/app-debug.apk`

## 🎯 功能特性

### 单词学习
- ✅ 单词搜索和添加
- ✅ 单词本管理
- ✅ 复习功能
- ✅ 学习进度跟踪
- ✅ 设置管理

### 技术特性
- ✅ 离线使用（数据库内置）
- ✅ 完整的API兼容性
- ✅ JavaScript接口通信
- ✅ 自适应界面

## 🔍 构建说明

### 详细文档
- `BUILD_INSTRUCTIONS_PYTHON.md` - 详细的构建步骤和故障排除
- `README_PYTHON.md` - 项目概述和特性说明

### 构建要求
- Android Studio (推荐版本 2022.1+)
- Java JDK 8+
- Android SDK (API 21+)
- 网络连接（首次构建需要下载Python解释器）

### 构建输出
- APK位置：`app/build/outputs/apk/debug/app-debug.apk`
- 大小：约 20-30MB（包含Python解释器）

## 🐍 Python集成

### Chaquopy配置
```gradle
plugins {
    id 'com.chaquo.python' version '15.0.2'
}

python {
    pip {
        install "flask"
    }
    pyc {
        srcDirs = ["src/main/python"]
    }
}
```

### Python依赖
- Flask: Web框架
- SQLite: 数据库（Python内置）
- 标准库：datetime, re, threading等

## 🚀 部署说明

### 首次运行
1. 安装APK到Android设备
2. 首次启动会初始化Python环境
3. 启动Flask服务器
4. 加载WebView界面

### 性能优化
- Python解释器预编译
- 数据库索引优化
- WebView缓存启用

## 🛠️ 故障排除

### 常见问题

1. **Python启动失败**
   - 检查Chaquopy版本
   - 查看logcat输出
   - 确认Python初始化

2. **数据库问题**
   - 确认数据库文件存在
   - 检查文件权限
   - 验证数据库完整性

3. **WebView问题**
   - 确认JavaScript已启用
   - 检查API URL配置
   - 验证网络权限

### 调试方法
- 使用Android Studio的logcat查看日志
- 检查Python错误输出
- 使用浏览器调试工具

## 📈 版本信息

- **当前版本**: 1.0
- **Python版本**: 3.8+
- **Android最低版本**: API 21 (Android 5.0)
- **构建工具**: Android Studio + Gradle

## 🤝 开发说明

### 代码修改
- Python代码保持不变
- 主要修改在MainActivity.kt
- 数据库路径适配Android环境

### 扩展功能
- 可以添加新的Python模块
- 支持pip安装额外依赖
- 可以集成其他Python库

---

## 🎉 总结

这个方案的最大优势是**保持原有Python代码不变**，只需要做很小的修改就可以在Android上运行！这样既保持了开发效率，又获得了Android应用的原生体验。

**立即开始构建：**
1. 运行 `BUILD_PYTHON_APK.bat`
2. 在Android Studio中打开项目
3. 构建并测试您的Python Android应用！