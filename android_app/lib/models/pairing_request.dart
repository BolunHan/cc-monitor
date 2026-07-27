class PairingRequest {
  final String id;
  final String deviceName;
  final DateTime requestedAt;
  final String status;

  const PairingRequest({
    required this.id,
    required this.deviceName,
    required this.requestedAt,
    required this.status,
  });

  factory PairingRequest.fromJson(Map<String, dynamic> json) {
    return PairingRequest(
      id: json['id'] as String,
      deviceName: json['device_name'] as String,
      requestedAt: DateTime.parse(json['requested_at'] as String),
      status: json['status'] as String,
    );
  }
}
