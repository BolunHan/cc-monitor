import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';

import 'api_client.dart';

class SseClient {
  final ApiClient _api;
  CancelToken? _cancelToken;
  StreamController<Map<String, dynamic>>? _controller;

  SseClient(this._api);

  Stream<Map<String, dynamic>> connect() {
    _controller?.close();
    _controller = StreamController<Map<String, dynamic>>.broadcast();
    _cancelToken = CancelToken();
    _startListening();
    return _controller!.stream;
  }

  Future<void> _startListening() async {
    int backoff = 1;
    const maxBackoff = 30;

    while (_cancelToken != null && !_cancelToken!.isCancelled) {
      try {
        final response = await _api.dio.get(
          '/api/stream',
          options: Options(
            responseType: ResponseType.stream,
            headers: {'Accept': 'text/event-stream'},
          ),
          cancelToken: _cancelToken,
        );

        final stream = response.data.stream as Stream<List<int>>;
        String buffer = '';

        await for (final chunk in stream) {
          buffer += utf8.decode(chunk);
          while (buffer.contains('\n\n')) {
            final idx = buffer.indexOf('\n\n');
            final event = buffer.substring(0, idx);
            buffer = buffer.substring(idx + 2);
            _parseEvent(event);
          }
        }

        // Connection closed — reconnect
        backoff = 1;
      } catch (e) {
        if (_cancelToken?.isCancelled ?? true) break;
        // Reconnect with backoff
        await Future.delayed(Duration(seconds: backoff));
        backoff = (backoff * 2).clamp(1, maxBackoff);
      }
    }
  }

  void _parseEvent(String block) {
    final lines = block.split('\n');
    String? event;
    String? data;

    for (final line in lines) {
      if (line.startsWith('event: ')) {
        event = line.substring(7);
      } else if (line.startsWith('data: ')) {
        data = line.substring(6);
      }
    }

    if (event != null && data != null) {
      try {
        final json = jsonDecode(data) as Map<String, dynamic>;
        json['_event_type'] = event;
        _controller?.add(json);
      } catch (_) {}
    }
  }

  void disconnect() {
    _cancelToken?.cancel();
    _cancelToken = null;
    _controller?.close();
    _controller = null;
  }
}
