import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../models/chat_message.dart';

/// An error whose [message] is safe and useful to show to the user.
class ApiException implements Exception {
  ApiException(this.message);
  final String message;

  @override
  String toString() => message;
}

/// Talks to the Aven backend. The API key is sent in the `X-Aven-Key` header
/// and is never logged or included in error messages.
class ApiClient {
  ApiClient({required String baseUrl, required this.apiKey, http.Client? client})
      : baseUrl = _normalize(baseUrl),
        _client = client ?? http.Client();

  final String baseUrl;
  final String apiKey;
  final http.Client _client;

  static const _timeout = Duration(seconds: 15);

  static String _normalize(String url) {
    final trimmed = url.trim().replaceAll(RegExp(r'/+$'), '');
    final uri = Uri.tryParse(trimmed);
    if (uri == null ||
        !(uri.scheme == 'http' || uri.scheme == 'https') ||
        uri.host.isEmpty) {
      throw ApiException('Enter a server address like http://10.0.2.2:8000');
    }
    return trimmed;
  }

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        'X-Aven-Key': apiKey,
      };

  Future<bool> health() async {
    try {
      final response =
          await _client.get(Uri.parse('$baseUrl/health')).timeout(_timeout);
      return response.statusCode == 200;
    } on Exception {
      return false;
    }
  }

  Future<AvenReply> chat(
    String message, {
    String? conversationId,
    bool private = false,
  }) async {
    final body = <String, dynamic>{'message': message, 'private': private};
    if (conversationId != null) body['conversation_id'] = conversationId;
    try {
      final response = await _client
          .post(
            Uri.parse('$baseUrl/api/v1/chat'),
            headers: _headers,
            body: jsonEncode(body),
          )
          .timeout(_timeout);
      return _parse(response);
    } on TimeoutException {
      throw ApiException('The server took too long to answer. Try again.');
    } on SocketException {
      throw ApiException(
          "Can't reach the Aven server. Check that it is running and the address is right.");
    } on http.ClientException {
      throw ApiException(
          "Can't reach the Aven server. Check that it is running and the address is right.");
    }
  }

  AvenReply _parse(http.Response response) {
    switch (response.statusCode) {
      case 200:
        try {
          final decoded = jsonDecode(utf8.decode(response.bodyBytes));
          return AvenReply.fromJson(decoded as Map<String, dynamic>);
        } on FormatException {
          throw ApiException('The server sent a reply I could not read.');
        } on TypeError {
          throw ApiException('The server sent a reply I could not read.');
        }
      case 401:
        throw ApiException('The server rejected the API key. Check it in Settings.');
      case 422:
        throw ApiException('That message was not accepted (too long or invalid).');
      case 429:
        throw ApiException('Too many requests. Wait a moment and try again.');
      default:
        throw ApiException('The server returned an error (${response.statusCode}).');
    }
  }

  void close() => _client.close();
}
