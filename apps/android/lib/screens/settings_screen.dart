import 'package:flutter/material.dart';

import '../services/api_client.dart';
import '../services/settings_store.dart';

/// Server address and API key. The key is stored in Android secure storage.
class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key, SettingsStore? store})
      : _store = store;

  final SettingsStore? _store;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late final SettingsStore _store = widget._store ?? SettingsStore();
  final _url = TextEditingController();
  final _key = TextEditingController();
  bool _loading = true;
  String? _status;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _url.dispose();
    _key.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final s = await _store.load();
    if (!mounted) return;
    setState(() {
      _url.text = s.baseUrl;
      _key.text = s.apiKey;
      _loading = false;
    });
  }

  Future<void> _save() async {
    try {
      ApiClient(baseUrl: _url.text, apiKey: _key.text).close(); // validates the URL
    } on ApiException catch (e) {
      setState(() => _status = e.message);
      return;
    }
    await _store.save(
      ConnectionSettings(baseUrl: _url.text, apiKey: _key.text),
    );
    if (!mounted) return;
    setState(() => _status = 'Saved.');
  }

  Future<void> _test() async {
    setState(() => _status = 'Testing…');
    try {
      final client = ApiClient(baseUrl: _url.text, apiKey: _key.text);
      final ok = await client.health();
      client.close();
      if (!mounted) return;
      setState(() => _status = ok
          ? 'Server reachable. (The API key is checked when you send a message.)'
          : "Can't reach the server at that address.");
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _status = e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                const Text(
                  'Android emulator: use http://10.0.2.2:8000. '
                  'Physical phone: use your PC\'s Wi-Fi address (see docs/setup-android.md).',
                ),
                const SizedBox(height: 16),
                TextField(
                  controller: _url,
                  keyboardType: TextInputType.url,
                  decoration: const InputDecoration(
                    labelText: 'Server address',
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _key,
                  obscureText: true,
                  enableSuggestions: false,
                  autocorrect: false,
                  decoration: const InputDecoration(
                    labelText: 'API key (AVEN_AI_API_KEY)',
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 16),
                Row(
                  children: [
                    FilledButton(onPressed: _save, child: const Text('Save')),
                    const SizedBox(width: 12),
                    OutlinedButton(
                        onPressed: _test, child: const Text('Test connection')),
                  ],
                ),
                if (_status != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 16),
                    child: Text(_status!),
                  ),
              ],
            ),
    );
  }
}
