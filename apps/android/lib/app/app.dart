import 'package:flutter/material.dart';

import '../screens/chat_screen.dart';
import '../services/api_client.dart';
import '../services/settings_store.dart';
import '../state/chat_controller.dart';

class AvenApp extends StatefulWidget {
  const AvenApp({super.key});

  @override
  State<AvenApp> createState() => _AvenAppState();
}

class _AvenAppState extends State<AvenApp> {
  final _settings = SettingsStore();
  late final ChatController _controller = ChatController(_makeClient);

  /// Reads the latest saved settings for every message, so changes made in the
  /// Settings screen apply immediately.
  Future<ApiClient?> _makeClient() async {
    final s = await _settings.load();
    if (!s.isComplete) return null;
    return ApiClient(baseUrl: s.baseUrl, apiKey: s.apiKey);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Aven AI',
      debugShowCheckedModeBanner: false,
      themeMode: ThemeMode.dark,
      darkTheme: ThemeData(
        useMaterial3: true,
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF0B1020),
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF22D3EE),
          secondary: const Color(0xFF7C3AED),
          brightness: Brightness.dark,
        ),
      ),
      home: ChatScreen(controller: _controller),
    );
  }
}
