import 'package:flutter/foundation.dart';
import '../models/pairing_request.dart';

class PairingProvider extends ChangeNotifier {
  List<PairingRequest> _pendingRequests = [];
  DateTime? _tokenExpiresAt;

  List<PairingRequest> get pendingRequests => List.unmodifiable(_pendingRequests);
  DateTime? get tokenExpiresAt => _tokenExpiresAt;
  bool get tokenExpiringSoon {
    if (_tokenExpiresAt == null) return false;
    return _tokenExpiresAt!.difference(DateTime.now()).inHours < 24;
  }

  void onPairingRequestEvent(Map<String, dynamic> data) {
    _pendingRequests.add(PairingRequest.fromJson(data));
    notifyListeners();
  }

  void removeRequest(String id) {
    _pendingRequests.removeWhere((r) => r.id == id);
    notifyListeners();
  }

  void updateTokenExpiry(DateTime expiresAt) {
    _tokenExpiresAt = expiresAt;
    notifyListeners();
  }
}
