import 'package:connectivity_plus/connectivity_plus.dart';

class ConnectivityService {
  ConnectivityService(this._connectivity);
  final Connectivity _connectivity;
  Future<bool> get isOnline async => !(await _connectivity.checkConnectivity())
      .contains(ConnectivityResult.none);
}
