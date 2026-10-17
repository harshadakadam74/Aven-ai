import 'package:flutter/foundation.dart';

import '../models/chat_message.dart';
import '../services/api_client.dart';

enum AvenState { idle, thinking, error }

typedef ClientFactory = Future<ApiClient?> Function();

/// Holds the conversation and talks to the backend. [clientFactory] returns
/// null when the server address / API key have not been set up yet.
class ChatController extends ChangeNotifier {
  ChatController(this._clientFactory) {
    _messages.add(ChatMessage(
      sender: Sender.aven,
      text: 'Hi! Connect to your Aven server in Settings, then say hello.',
    ));
  }

  final ClientFactory _clientFactory;
  final List<ChatMessage> _messages = [];
  String? _conversationId;
  AvenState _state = AvenState.idle;
  String? _lastFailedText;

  List<ChatMessage> get messages => List.unmodifiable(_messages);
  AvenState get state => _state;
  bool get busy => _state == AvenState.thinking;
  String? get lastFailedText => _lastFailedText;

  Future<void> send(String text) async {
    final trimmed = text.trim();
    if (trimmed.isEmpty || busy) return;
    _messages.add(ChatMessage(sender: Sender.user, text: trimmed));
    _lastFailedText = null;
    _state = AvenState.thinking;
    notifyListeners();

    try {
      final client = await _clientFactory();
      if (client == null) {
        throw ApiException('Open Settings and enter your server address and API key first.');
      }
      final reply = await client.chat(trimmed, conversationId: _conversationId);
      _conversationId = reply.conversationId;
      _messages.add(ChatMessage(sender: Sender.aven, text: reply.text));
      _state = AvenState.idle;
    } on ApiException catch (e) {
      _fail(trimmed, e.message);
    } catch (_) {
      _fail(trimmed, 'Something unexpected went wrong. Please try again.');
    }
    notifyListeners();
  }

  Future<void> retry() async {
    final text = _lastFailedText;
    if (text != null) await send(text);
  }

  void newConversation() {
    _conversationId = null;
    _messages
      ..clear()
      ..add(ChatMessage(sender: Sender.aven, text: 'Started a new conversation.'));
    _state = AvenState.idle;
    _lastFailedText = null;
    notifyListeners();
  }

  void _fail(String text, String message) {
    _lastFailedText = text;
    _messages.add(ChatMessage(sender: Sender.aven, text: message, isError: true));
    _state = AvenState.error;
  }
}
