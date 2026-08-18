import 'package:dio/dio.dart';

/// Why a request failed, in terms the presentation layer can localize.
///
/// This is deliberately a small closed set rather than the raw
/// [DioExceptionType]: the UI needs to pick one of a handful of sentences,
/// and matching on transport enum values in every screen would spread that
/// decision around.
enum NetworkFailure { offline, timeout, badResponse, unknown }

class NetworkException implements Exception {
  const NetworkException(
    this.detail, {
    this.statusCode,
    this.failure = NetworkFailure.unknown,
  });

  /// The server's own message, when it sent one.
  ///
  /// It is English prose written by the backend, so it is **not** shown to
  /// the user directly — `describeError` turns the status code into a
  /// translated sentence instead. It is kept for logging and for the few
  /// developer-facing surfaces that want the raw text.
  final String? detail;

  final int? statusCode;
  final NetworkFailure failure;

  bool get isOffline => failure == NetworkFailure.offline;

  @override
  String toString() => detail ?? 'NetworkException($failure, $statusCode)';

  factory NetworkException.fromDio(DioException error) {
    final data = error.response?.data;
    final detail = data is Map ? data['detail'] : null;
    return NetworkException(
      detail is String ? detail : null,
      statusCode: error.response?.statusCode,
      failure: switch (error.type) {
        DioExceptionType.connectionError => NetworkFailure.offline,
        DioExceptionType.connectionTimeout ||
        DioExceptionType.sendTimeout ||
        DioExceptionType.receiveTimeout => NetworkFailure.timeout,
        DioExceptionType.badResponse => NetworkFailure.badResponse,
        _ => NetworkFailure.unknown,
      },
    );
  }
}
