import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../l10n/l10n_labels.dart';
import 'struct_nav_bar.dart';

export 'struct_nav_bar.dart' show ShellDestination, NavCenterAction;

/// The frame every tabbed screen sits in.
///
/// It owns exactly two things: which destination is current, and the bar that
/// says so. Screens keep their own [Scaffold] (and therefore their own app
/// bar and their own FAB); the shell only supplies the bottom edge.
class MobileShell extends StatelessWidget {
  const MobileShell({
    super.key,
    required this.child,
    required this.location,
    required this.destinations,
    this.showVoiceAction = false,
  });

  final Widget child;
  final String location;
  final List<ShellDestination> destinations;

  /// Whether the raised centre action (voice capture) is offered. Decided by
  /// `canUseVoice`, which is every role but Admin.
  final bool showVoiceAction;

  @override
  Widget build(BuildContext context) {
    // Longest path first, so '/reviews/42' selects '/reviews' rather than
    // whichever destination happens to be a prefix of it.
    var selected = -1;
    var bestLength = -1;
    for (var index = 0; index < destinations.length; index++) {
      final path = destinations[index].path;
      if (location == path || location.startsWith('$path/')) {
        if (path.length > bestLength) {
          bestLength = path.length;
          selected = index;
        }
      }
    }
    return Scaffold(
      body: SafeArea(top: false, bottom: false, child: child),
      bottomNavigationBar: StructNavBar(
        destinations: destinations,
        selectedIndex: selected,
        onSelected: (index) => context.go(destinations[index].path),
        centerAction: showVoiceAction
            ? NavCenterAction(
                icon: Icons.mic_rounded,
                label: context.l10n.navVoiceAssistant,
                onPressed: () => context.push('/voice'),
              )
            : null,
      ),
    );
  }
}
