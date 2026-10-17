enum Sender { user, aven }

class ChatMessage {
  ChatMessage({required this.sender, required this.text, this.isError = false})
      : time = DateTime.now();

  final Sender sender;
  final String text;
  final bool isError;
  final DateTime time;
}

/// Response from `POST /api/v1/chat`.
class AvenReply {
  const AvenReply({
    required this.text,
    required this.intent,
    required this.conversationId,
    required this.language,
    this.needsInput,
  });

  final String text;
  final String intent;
  final String conversationId;
  final String language;
  final String? needsInput;

  factory AvenReply.fromJson(Map<String, dynamic> json) {
    final text = json['text'];
    final conversationId = json['conversation_id'];
    if (text is! String || conversationId is! String) {
      throw const FormatException('Unexpected reply from the server');
    }
    return AvenReply(
      text: text,
      intent: (json['intent'] as String?) ?? 'unknown',
      conversationId: conversationId,
      language: (json['language'] as String?) ?? 'en',
      needsInput: json['needs_input'] as String?,
    );
  }
}
