import 'package:dio/dio.dart';

import '../../app/app_config.dart';
import '../constants/api_endpoints.dart';
import '../storage/secure_storage_service.dart';
import 'network_exceptions.dart';

class ApiClient {
  ApiClient(AppConfig config, this._storage)
    : _dio = Dio(
        BaseOptions(
          baseUrl: config.apiBaseUrl,
          connectTimeout: const Duration(seconds: 15),
          receiveTimeout: const Duration(seconds: 30),
          headers: const {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
          },
        ),
      ) {
    _dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          final token = await _storage.accessToken;
          if (token != null) options.headers['Authorization'] = 'Bearer $token';
          handler.next(options);
        },
        onError: (error, handler) async {
          final request = error.requestOptions;
          if (error.response?.statusCode == 401 &&
              request.extra['retried'] != true &&
              !request.path.endsWith(ApiEndpoints.refresh)) {
            try {
              final refreshToken = await _storage.refreshToken;
              if (refreshToken == null) return handler.next(error);
              final response = await _dio.post<Map<String, dynamic>>(
                ApiEndpoints.refresh,
                data: {'refresh_token': refreshToken},
                options: Options(headers: {'Authorization': null}),
              );
              final data = response.data!;
              await _storage.saveTokens(
                data['access_token'] as String,
                data['refresh_token'] as String? ?? refreshToken,
              );
              request.extra['retried'] = true;
              request.headers['Authorization'] =
                  'Bearer ${data['access_token']}';
              return handler.resolve(await _dio.fetch(request));
            } catch (_) {
              await _storage.clearTokens();
            }
          }
          handler.next(error);
        },
      ),
    );
  }

  final Dio _dio;
  final SecureStorageService _storage;

  Future<T> get<T>(String path, {Map<String, dynamic>? query}) =>
      _request(() => _dio.get<T>(path, queryParameters: query));
  Future<T> post<T>(String path, {Object? data}) =>
      _request(() => _dio.post<T>(path, data: data));
  Future<T> postForm<T>(String path, Map<String, dynamic> data) => _request(
    () => _dio.post<T>(
      path,
      data: data,
      options: Options(contentType: Headers.formUrlEncodedContentType),
    ),
  );
  Future<T> put<T>(String path, {Object? data, Map<String, dynamic>? query}) =>
      _request(() => _dio.put<T>(path, data: data, queryParameters: query));
  Future<T> upload<T>(
    String path,
    FormData data, {
    ProgressCallback? onSendProgress,
  }) => _request(
    () => _dio.post<T>(
      path,
      data: data,
      onSendProgress: onSendProgress,
      options: Options(contentType: 'multipart/form-data'),
    ),
  );

  Future<T> _request<T>(Future<Response<T>> Function() request) async {
    try {
      final response = await request();
      return response.data as T;
    } on DioException catch (error) {
      throw NetworkException.fromDio(error);
    }
  }
}
