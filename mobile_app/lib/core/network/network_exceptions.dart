import 'package:dio/dio.dart';

class NetworkException implements Exception {
  const NetworkException(
    this.message, {
    this.statusCode,
    this.isOffline = false,
  });
  final String message;
  final int? statusCode;
  final bool isOffline;

  factory NetworkException.fromDio(DioException error) {
    final data = error.response?.data;
    final detail = data is Map ? data['detail'] : null;
    return NetworkException(
      detail is String ? detail : _fallback(error),
      statusCode: error.response?.statusCode,
      isOffline: error.type == DioExceptionType.connectionError,
    );
  }

  static String _fallback(DioException error) {
    if (error.type == DioExceptionType.connectionTimeout ||
        error.type == DioExceptionType.receiveTimeout) {
      return 'The server took too long to respond. Please retry.';
    }
    if (error.type == DioExceptionType.connectionError) {
      return 'Cannot reach the project server. Check that the server is '
          'running and that this device is on the correct network.';
    }
    return 'Something went wrong. Please try again.';
  }
}
