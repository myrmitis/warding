// swift-tools-version: 5.9
import PackageDescription

// Build both speech helpers without changing the Python launcher's compiler or cache.
let package = Package(
    name: "WardingAppleSpeech",
    platforms: [.macOS("26.0")],
    products: [
        .executable(name: "AppleTranscribe", targets: ["AppleTranscribe"]),
        .executable(name: "StreamTranscribe", targets: ["StreamTranscribe"]),
    ],
    targets: [
        .executableTarget(
            name: "AppleTranscribe",
            path: "src/warding/apple_speech",
            exclude: ["__init__.py", "StreamTranscribe.swift"],
            sources: ["AppleTranscribe.swift"]
        ),
        .executableTarget(
            name: "StreamTranscribe",
            path: "src/warding/apple_speech",
            exclude: ["__init__.py", "AppleTranscribe.swift"],
            sources: ["StreamTranscribe.swift"]
        ),
    ],
    swiftLanguageVersions: [.v5]
)
