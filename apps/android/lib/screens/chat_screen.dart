import 'package:flutter/material.dart';

import '../models/chat_message.dart';
import '../state/chat_controller.dart';
import '../widgets/orb.dart';
import 'settings_screen.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key, required this.controller});

  final ChatController controller;

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _input = TextEditingController();
  final _scroll = ScrollController();

  @override
  void dispose() {
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    final text = _input.text;
    if (text.trim().isEmpty) return;
    _input.clear();
    await widget.controller.send(text);
    if (_scroll.hasClients) {
      _scroll.animateTo(
        _scroll.position.maxScrollExtent + 120,
        duration: const Duration(milliseconds: 250),
        curve: Curves.easeOut,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.controller;
    return ListenableBuilder(
      listenable: c,
      builder: (context, _) {
        return Scaffold(
          appBar: AppBar(
            title: const Text('Aven AI'),
            actions: [
              IconButton(
                tooltip: 'New chat',
                icon: const Icon(Icons.add_comment_outlined),
                onPressed: c.newConversation,
              ),
              IconButton(
                tooltip: 'Settings',
                icon: const Icon(Icons.settings_outlined),
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const SettingsScreen()),
                ),
              ),
            ],
          ),
          body: SafeArea(
            child: Column(
              children: [
                const SizedBox(height: 8),
                AvenOrb(state: c.state, size: 110),
                Text(
                  switch (c.state) {
                    AvenState.idle => 'Idle',
                    AvenState.thinking => 'Thinking…',
                    AvenState.error => 'Error',
                  },
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                Expanded(
                  child: ListView.builder(
                    controller: _scroll,
                    padding: const EdgeInsets.all(16),
                    itemCount: c.messages.length,
                    itemBuilder: (_, i) => _Bubble(message: c.messages[i]),
                  ),
                ),
                if (c.lastFailedText != null)
                  TextButton.icon(
                    onPressed: c.retry,
                    icon: const Icon(Icons.refresh),
                    label: const Text('Retry last message'),
                  ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
                  child: Row(
                    children: [
                      const IconButton(
                        tooltip: 'Voice input arrives in Stage 2',
                        icon: Icon(Icons.mic_off_outlined),
                        onPressed: null, // disabled until Stage 2
                      ),
                      Expanded(
                        child: TextField(
                          controller: _input,
                          textInputAction: TextInputAction.send,
                          maxLength: 2000,
                          decoration: const InputDecoration(
                            hintText: 'Type a message',
                            counterText: '',
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.all(Radius.circular(16)),
                            ),
                          ),
                          onSubmitted: (_) => _send(),
                        ),
                      ),
                      const SizedBox(width: 8),
                      IconButton.filled(
                        tooltip: 'Send',
                        icon: const Icon(Icons.send),
                        onPressed: c.busy ? null : _send,
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _Bubble extends StatelessWidget {
  const _Bubble({required this.message});

  final ChatMessage message;

  @override
  Widget build(BuildContext context) {
    final isUser = message.sender == Sender.user;
    final scheme = Theme.of(context).colorScheme;
    final background = message.isError
        ? scheme.errorContainer
        : isUser
            ? scheme.primaryContainer
            : scheme.surfaceContainerHighest;
    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        constraints:
            BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.8),
        decoration: BoxDecoration(
          color: background,
          borderRadius: BorderRadius.circular(16),
        ),
        child: SelectableText(message.text),
      ),
    );
  }
}
