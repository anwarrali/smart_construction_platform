import 'package:flutter_test/flutter_test.dart';

import 'package:construction_field/core/push/push_controller.dart';

/// What a tapped notification opens.
///
/// This mapping is the part of push most likely to rot: screens get added and
/// routes get renamed, and the failure mode is a notification that opens the
/// wrong screen — or crashes on a route that no longer exists. It is pure, so
/// it is cheap to pin here rather than discovering it on a phone.
void main() {
  group('routeForEntity', () {
    test('a task notification opens that exact task', () {
      expect(routeForEntity('TASK', 'abc-123'), '/tasks/abc-123');
    });

    test('entity types are matched case-insensitively', () {
      // The backend writes them upper-case, but a payload round-trips through
      // FCM as untyped strings and this should not be the thing that breaks.
      expect(routeForEntity('task', 'abc-123'), '/tasks/abc-123');
    });

    test('entities with a list screen but no detail screen open the list', () {
      expect(routeForEntity('ISSUE', 'i-1'), '/issues');
      expect(routeForEntity('SITE_REPORT', 'r-1'), '/reports');
      expect(routeForEntity('DESIGN_CHANGE', 'd-1'), '/design-changes');
      expect(routeForEntity('FIELD_SUBMISSION', 'f-1'), '/evidence');
    });

    test('owner requests and site visits share the actions screen', () {
      expect(routeForEntity('OWNER_REQUEST', 'o-1'), '/actions');
      expect(routeForEntity('SITE_VISIT', 'v-1'), '/actions');
    });

    test('an entity this app has no screen for resolves to nothing', () {
      // Rather than inventing a route: the caller falls back to the
      // notification detail screen, which always exists. IFC comparisons and
      // AI insights are web-only today.
      expect(routeForEntity('IFC_COMPARISON', 'c-1'), isNull);
      expect(routeForEntity('AI_INSIGHT', 'a-1'), isNull);
    });

    test('a missing or empty id never produces a route', () {
      // '/tasks/' would match the route pattern and then fail to load.
      expect(routeForEntity('TASK', null), isNull);
      expect(routeForEntity('TASK', ''), isNull);
      expect(routeForEntity(null, 'abc-123'), isNull);
    });
  });
}
