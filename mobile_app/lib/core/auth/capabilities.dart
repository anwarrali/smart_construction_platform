import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/dependency_injection.dart';
import '../constants/api_endpoints.dart';
import '../network/api_client.dart';

/// What the signed-in person may do, as the server resolved it.
///
/// The client used to answer this from role names — `user.isSiteEngineer`,
/// `user.isConsultant`, `role == RoleConstants.admin`. That could not survive
/// a consulting office configuring its own roles: an office that creates
/// "Resident Engineer" has no branch in such a table, and two offices can give
/// the same job title different authority.
///
/// So the answer comes from `GET /access-control/me`, which is the same
/// resolution every endpoint performs — office role, project role, per-person
/// overrides, then the external ceilings.
///
/// **This is presentation only.** It decides which buttons and tabs to draw.
/// Every protected operation is checked again on the server when it is
/// attempted, and nothing here is or may become a security boundary: a stale
/// or over-generous answer costs a wasted tap and a 403, never access.
class Capabilities {
  const Capabilities(this._codes, {this.isReady = true});

  /// Before the answer has arrived. Every check returns true, so navigation
  /// renders optimistically rather than flickering in as permissions load —
  /// the server refuses anything that was not really allowed.
  const Capabilities.pending() : this(const <String>{}, isReady: false);

  final Set<String> _codes;
  final bool isReady;

  bool has(String code) => !isReady || _codes.contains(code);

  bool hasAny(Iterable<String> codes) =>
      !isReady || codes.any(_codes.contains);

  /// Exposed for diagnostics and tests; not for building rules out of.
  Set<String> get codes => Set.unmodifiable(_codes);
}

/// Fetches the caller's effective permissions, optionally for one project.
///
/// Project-scoped, because the answer genuinely differs per project: the same
/// person can be office staff on one and a contractor's representative on
/// another, and the external ceiling applies to the second and not the first.
class CapabilityRepository {
  const CapabilityRepository(this._client);

  final ApiClient _client;

  Future<Capabilities> fetch({String? projectId}) async {
    final response = await _client.get<List<dynamic>>(
      ApiEndpoints.myPermissions,
      query: projectId == null ? null : {'project_id': projectId},
    );
    return Capabilities(response.map((item) => '$item').toSet());
  }
}

final capabilityRepositoryProvider = Provider<CapabilityRepository>(
  (ref) => CapabilityRepository(ref.watch(apiClientProvider)),
);

/// The caller's capabilities for a project, or platform-wide when null.
///
/// `AsyncValue` rather than a plain future so a screen can render its
/// optimistic state while the answer is in flight; `capabilitiesOf` folds that
/// into a [Capabilities] whose `isReady` is false, which is what makes the
/// optimistic default a single decision rather than one per call site.
final capabilitiesProvider =
    FutureProvider.family<Capabilities, String?>((ref, projectId) async {
  return ref.watch(capabilityRepositoryProvider).fetch(projectId: projectId);
});

/// The reading most widgets want: never throws, never null, safe before load.
Capabilities capabilitiesOf(WidgetRef ref, {String? projectId}) =>
    _fold(ref.watch(capabilitiesProvider(projectId)));

/// The same reading from inside another provider, where the handle is a [Ref]
/// rather than a [WidgetRef]. Two entry points because Riverpod's two handles
/// are unrelated types, not because the answer differs.
Capabilities capabilitiesFrom(Ref ref, {String? projectId}) =>
    _fold(ref.watch(capabilitiesProvider(projectId)));

Capabilities _fold(AsyncValue<Capabilities> value) => value.maybeWhen(
      data: (resolved) => resolved,
      orElse: () => const Capabilities.pending(),
    );
