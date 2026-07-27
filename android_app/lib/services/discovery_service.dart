import 'package:multicast_dns/multicast_dns.dart';

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
    _client = MDnsClient();
    await _client!.start();

    final servers = <DiscoveredServer>[];

    try {
      await for (final ptr in _client!.lookup<PtrResourceRecord>(
        ResourceRecordQuery.serverPointer('_cc-monitor._tcp.local'),
      )) {
        try {
          final srvList = await _client!
              .lookup<SrvResourceRecord>(
                ResourceRecordQuery.service(ptr.domainName),
              )
              .toList();
          final txtList = await _client!
              .lookup<TxtResourceRecord>(
                ResourceRecordQuery.text(ptr.domainName),
              )
              .toList();

          if (srvList.isNotEmpty && txtList.isNotEmpty) {
            final txtMap = <String, String>{};
            for (final entry in txtList.first.text.split('\n')) {
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
          }
        } catch (_) {
          // Skip servers with incomplete DNS records
        }
      }
    } catch (_) {
      // mDNS discovery failed
    }

    _client!.stop();
    return servers;
  }

  void stop() {
    _client?.stop();
  }
}
