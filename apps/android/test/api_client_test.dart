import 'dart:convert';
import 'dart:io';

import 'package:aven_ai/services/api_client.dart';
import 'package:aven_ai/state/chat_controller.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

http.Response _json(Object body, [int status = 200]) => http.Response(
      jsonEncode(body),
      status,
      headers: {'content-type': 'application/json; charset=utf-8'},
    );

const _okBody = {
  'text': 'Hey! I am here.',
  'intent': 'greeting',
  'conversation_id': 'abc123',
  'language': 'en',
};

void main() {
  group('ApiClient', () {
    test('sends the API key header and JSON body, parses the reply', () async {
      late http.Request seen;
      final client = ApiClient(
        baseUrl: 'http://10.0.2.2:8000/',
        apiKey: 'secret-key',
        client: MockClient((request) async {
          seen = request;
          return _json(_okBody);
        }),
      );
      final reply = await client.chat('hello', conversationId: 'abc123');
      expect(seen.url.toString(), 'http://10.0.2.2:8000/api/v1/chat');
      expect(seen.headers['X-Aven-Key'], 'secret-key');
      expect(jsonDecode(seen.body)['conversation_id'], 'abc123');
      expect(reply.text, 'Hey! I am here.');
      expect(reply.conversationId, 'abc123');
    });

    test('maps HTTP errors to friendly messages without leaking the key', () async {
      Future<String> messageFor(int status) async {
        final client = ApiClient(
          baseUrl: 'http://x.test',
          apiKey: 'secret-key',
          client: MockClient((_) async => _json({'detail': 'nope'}, status)),
        );
        try {
          await client.chat('hi');
        } on ApiException catch (e) {
          return e.message;
        }
        return 'no error';
      }

      expect(await messageFor(401), contains('API key'));
      expect(await messageFor(429), contains('Too many'));
      expect(await messageFor(500), contains('500'));
      for (final status in [401, 422, 429, 500]) {
        expect(await messageFor(status), isNot(contains('secret-key')));
      }
    });

    test('network failure becomes a readable error', () async {
      final client = ApiClient(
        baseUrl: 'http://x.test',
        apiKey: 'k',
        client: MockClient((_) async => throw const SocketException('down')),
      );
      expect(
        () => client.chat('hi'),
        throwsA(isA<ApiException>()
            .having((e) => e.message, 'message', contains("Can't reach"))),
      );
    });

    test('rejects malformed server addresses', () {
      for (final bad in ['', 'not a url', 'ftp://x', 'http://']) {
        expect(() => ApiClient(baseUrl: bad, apiKey: 'k'),
            throwsA(isA<ApiException>()),
            reason: bad);
      }
    });

    test('garbage reply body is reported, not thrown raw', () async {
      final client = ApiClient(
        baseUrl: 'http://x.test',
        apiKey: 'k',
        client: MockClient((_) async => http.Response('<html>', 200)),
      );
      expect(() => client.chat('hi'), throwsA(isA<ApiException>()));
    });
  });

  group('ChatController', () {
    test('keeps the conversation id and appends messages', () async {
      final bodies = <Map<String, dynamic>>[];
      final controller = ChatController(() async => ApiClient(
            baseUrl: 'http://x.test',
            apiKey: 'k',
            client: MockClient((request) async {
              bodies.add(jsonDecode(request.body));
              return _json(_okBody);
            }),
          ));
      await controller.send('hello');
      await controller.send('again');
      expect(bodies[0].containsKey('conversation_id'), isFalse);
      expect(bodies[1]['conversation_id'], 'abc123');
      expect(controller.state, AvenState.idle);
      expect(controller.messages.length, 5); // intro + 2 user + 2 aven
    });

    test('unconfigured client explains what to do and allows retry', () async {
      final controller = ChatController(() async => null);
      await controller.send('hello');
      expect(controller.state, AvenState.error);
      expect(controller.messages.last.isError, isTrue);
      expect(controller.lastFailedText, 'hello');
    });
  });
}
