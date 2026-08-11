import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:multicast_dns/multicast_dns.dart';

const _tag = 'cc-monitor:discovery';

const _probePort = 9876;

class DiscoveredServer {
  final String hostname;
  final String host;
  final int port;
  final String version;
  final String certSha256;
  final bool pairingRequired;

  const DiscoveredServer({
    required this.hostname,
    required this.host,
    required this.port,
    required this.version,
    required this.certSha256,
    required this.pairingRequired,
  });
}

class DiscoveryService {
  MDnsClient? _client;

  Future<List<DiscoveredServer>> discover() async {
    // mDNS multicast does not traverse WireGuard/VPN tunnels, so also
    // unicast-probe the /24 subnets of every active interface (the WG
    // tun included).  mDNS results win on duplicate host:port.
    final results = await Future.wait([
      _mdnsScan(),
      _probeSubnets(),
    ]);
    // mDNS entries carry richer metadata — keep them, only fill gaps.
    final byKey = <String, DiscoveredServer>{};
    for (final s in results[0]) {
      byKey['${s.host}:${s.port}'] = s;
    }
    for (final s in results[1]) {
      byKey.putIfAbsent('${s.host}:${s.port}', () => s);
    }
    final unique = byKey.values.toList();
    debugPrint('[$_tag] Scan done: ${unique.length} unique servers');
    return unique;
  }

  Future<List<DiscoveredServer>> _mdnsScan() async {
    debugPrint('[$_tag] Starting mDNS scan for _cc-monitor._tcp...');
    _client = MDnsClient();
    await _client!.start();

    final servers = <DiscoveredServer>[];

    try {
      await for (final ptr in _client!.lookup<PtrResourceRecord>(
        ResourceRecordQuery.serverPointer('_cc-monitor._tcp.local'),
      )) {
        debugPrint('[$_tag] Found PTR: ${ptr.domainName}');
        try {
          await _client!
              .lookup<SrvResourceRecord>(
                ResourceRecordQuery.service(ptr.domainName),
              )
              .first
              .timeout(const Duration(seconds: 3));
          final txt = await _client!
              .lookup<TxtResourceRecord>(
                ResourceRecordQuery.text(ptr.domainName),
              )
              .first
              .timeout(const Duration(seconds: 3));

          final txtMap = <String, String>{};
          for (final entry in txt.text.split('\n')) {
            final parts = entry.split('=');
            if (parts.length == 2) {
              txtMap[parts[0]] = parts[1];
            }
          }

          servers.add(DiscoveredServer(
            hostname: ptr.domainName.replaceAll('._cc-monitor._tcp.local', ''),
            host: txtMap['host'] ?? '',
            port: int.tryParse(txtMap['port'] ?? '') ?? 9876,
            version: txtMap['version'] ?? '',
            certSha256: txtMap['cert_sha256'] ?? '',
            pairingRequired: txtMap['pairing'] == 'required',
          ));
          debugPrint('[$_tag] Resolved: ${txtMap['host']}:${txtMap['port']}');
        } catch (e) {
          debugPrint('[$_tag] Incomplete record: $e');
        }
      }
    } catch (e) {
      debugPrint('[$_tag] mDNS scan error: $e');
    }

    _client!.stop();
    return servers;
  }

  /// Probe https://<ip>:9876/api/version on every /24 subnet of the
  /// active IPv4 interfaces.  Unicast — works over WireGuard where
  /// mDNS multicast is not forwarded.
  Future<List<DiscoveredServer>> _probeSubnets() async {
    final candidates = <String>{};
    try {
      final interfaces = await NetworkInterface.list(
        includeLoopback: false,
        type: InternetAddressType.IPv4,
      );
      for (final iface in interfaces) {
        for (final addr in iface.addresses) {
          final parts = addr.address.split('.');
          if (parts.length != 4) continue;
          final base = '${parts[0]}.${parts[1]}.${parts[2]}';
          for (var i = 1; i <= 254; i++) {
            final ip = '$base.$i';
            if (ip != addr.address) candidates.add(ip);
          }
        }
      }
    } catch (e) {
      debugPrint('[$_tag] Interface enumeration failed: $e');
      return [];
    }

    if (candidates.isEmpty) return [];
    final list = candidates.take(700).toList(); // bound scan size
    debugPrint(
        '[$_tag] Unicast probing ${list.length} candidates on port $_probePort...');

    final servers = <DiscoveredServer>[];
    final dio = Dio(BaseOptions(
      connectTimeout: const Duration(milliseconds: 300),
      receiveTimeout: const Duration(milliseconds: 800),
      validateStatus: (_) => true,
    ));
    // Self-signed cert is expected — we only care that /api/version answers
    (dio.httpClientAdapter as dynamic).onHttpClientCreate = (HttpClient client) {
      client.badCertificateCallback = (cert, host, port) => true;
    };

    const concurrency = 48;
    for (var i = 0; i < list.length; i += concurrency) {
      final batch = list.skip(i).take(concurrency);
      await Future.wait(batch.map((ip) async {
        try {
          final resp = await dio.get('https://$ip:$_probePort/api/version');
          final data = resp.data;
          if (resp.statusCode == 200 && data is Map && data['version'] is String) {
            debugPrint('[$_tag] Probe hit: $ip (v${data['version']})');
            servers.add(DiscoveredServer(
              hostname: ip,
              host: ip,
              port: _probePort,
              version: data['version'] as String,
              certSha256: '',
              pairingRequired: true,
            ));
          }
        } catch (_) {
          // Unreachable host / not a cc-monitor server — ignore.
        }
      }));
    }
    return servers;
  }

  void stop() {
    _client?.stop();
  }
}
