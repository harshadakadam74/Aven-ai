import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class ConnectionSettings {
  const ConnectionSettings({required this.baseUrl, required this.apiKey});

  final String baseUrl;
  final String apiKey;

  bool get isComplete => baseUrl.isNotEmpty && apiKey.isNotEmpty;
}

/// Persists the server address and API key in platform-backed secure storage
/// (Android Keystore). Nothing sensitive goes in plain preferences or source.
class SettingsStore {
  SettingsStore([FlutterSecureStorage? storage])
      : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;

  /// 10.0.2.2 is how the Android emulator reaches the host PC's localhost.
  static const defaultBaseUrl = 'http://10.0.2.2:8000';

  static const _urlKey = 'aven_base_url';
  static const _keyKey = 'aven_api_key';

  Future<ConnectionSettings> load() async {
    final url = await _storage.read(key: _urlKey) ?? defaultBaseUrl;
    final key = await _storage.read(key: _keyKey) ?? '';
    return ConnectionSettings(baseUrl: url, apiKey: key);
  }

  Future<void> save(ConnectionSettings settings) async {
    await _storage.write(key: _urlKey, value: settings.baseUrl.trim());
    await _storage.write(key: _keyKey, value: settings.apiKey.trim());
  }
}
