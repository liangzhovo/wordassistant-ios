# 单词助手 Android APK

这是一个基于WebView的单词助手Android应用，将桌面版的Flask应用转换为APK格式。

## 项目结构

```
android-app/
├── app/
│   ├── src/
│   │   ├── main/
│   │   │   ├── java/
│   │   │   │   └── com/
│   │   │   │       └── example/
│   │   │   │           └── wordassistant/
│   │   │   │               ├── MainActivity.kt      # 主Activity
│   │   │   │               ├── DatabaseHelper.java  # 数据库助手
│   │   │   │               └── WebServer.java       # Web服务器
│   │   │   ├── assets/
│   │   │   │   ├── index.html                      # 前端界面
│   │   │   │   └── 简明英汉字典增强版.db           # 数据库文件
│   │   │   ├── AndroidManifest.xml
│   │   │   ├── res/
│   │   │   └── ...
│   │   └── build.gradle
│   └── proguard-rules.pro
├── build.gradle
├── settings.gradle
└── build_apk.bat                                  # 构建脚本
```

## 构建步骤

### 1. 环境要求

- Java JDK 8或更高版本
- Android SDK
- Android Build Tools
- Android NDK（可选，用于HTTP服务器）

### 2. 构建APK

使用提供的构建脚本：

```bash
# Windows
build_apk.bat
```

或者手动构建：

```bash
# 清理之前的构建
./gradlew clean

# 构建debug APK
./gradlew assembleDebug
```

构建完成后，APK文件位于：`app/build/outputs/apk/debug/app-debug.apk`

### 3. 安装APK

```bash
# 安装到连接的Android设备
adb install app/build/outputs/apk/debug/app-debug.apk
```

## 技术实现

### 核心组件

1. **MainActivity.kt**
   - 初始化WebView
   - 启动内置Web服务器
   - 提供JavaScript接口

2. **WebServer.java**
   - 基于Java HTTP服务器的后端API
   - 提供与原Flask应用相同的API端点
   - 处理SQLite数据库操作

3. **DatabaseHelper.java**
   - 管理SQLite数据库
   - 从assets复制数据库到应用私有目录
   - 提供数据库访问接口

4. **index.html**
   - 原有的前端界面
   - 修改API调用以适配内置服务器
   - 添加JavaScript接口支持

### API适配

原Flask应用的API端口为5000，在Android版本中改为8080。前端代码通过JavaScript接口动态获取API URL：

```javascript
function getApiUrl() {
    return window.Android ? window.Android.getApiUrl() : 'http://127.0.0.1:8080';
}
```

## 功能特性

- ✅ 单词搜索和添加
- ✅ 单词本管理
- ✅ 复习功能
- ✅ 学习进度跟踪
- ✅ 设置管理
- ✅ 离线使用（数据库内置）

## 注意事项

1. **首次启动**：应用首次启动时会从assets复制数据库文件，可能需要几秒钟时间。

2. **网络权限**：应用需要网络权限来启动内置服务器，但实际功能可以离线使用。

3. **性能**：由于使用内置HTTP服务器，性能可能不如原桌面版，但功能完整。

4. **兼容性**：支持Android 5.0 (API 21)及以上版本。

## 故障排除

### 构建错误

1. **找不到gradle**：确保安装了Android SDK并配置了环境变量。
2. **缺少依赖**：确保安装了Android Build Tools和NDK。

### 运行时错误

1. **应用启动失败**：检查AndroidManifest.xml中的权限配置。
2. **API调用失败**：确保Web服务器正常启动（端口8080）。

### 数据库问题

1. **数据库复制失败**：检查assets目录中的数据库文件是否存在。
2. **数据库访问错误**：确保DatabaseHelper正确初始化。

## 开发说明

如需修改应用，主要修改以下文件：

- `MainActivity.kt` - 主Activity逻辑
- `WebServer.java` - 后端API实现
- `DatabaseHelper.java` - 数据库操作
- `index.html` - 前端界面
- `AndroidManifest.xml` - 应用配置和权限

## 许可证

本项目基于原始的单词助手应用开发，保持相同的开源协议。