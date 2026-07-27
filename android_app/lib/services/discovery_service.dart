import 'package:flutter/foundation.dart';
import 'package:multicast_dns/multicast_dns.dart';

const _tag = 'cc-monitor:discovery';

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
          final srv = await _client!
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

    // Deduplicate: hash of identifying fields
    final seen = <String>{};
    final unique = servers.where((s) {
      return seen.add('${s.hostname}|${s.host}|${s.port}|${s.version}|${s.certSha256}');
    }).toList();
    debugPrint('[$_tag] Scan done: ${servers.length} raw, ${unique.length} unique');
    return unique;
  }

  void stop() {
    _client?.stop();
  }
}
