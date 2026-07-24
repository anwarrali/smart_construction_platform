import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../theme/app_colors.dart';

class MobileShell extends StatelessWidget {
  const MobileShell({
    super.key,
    required this.child,
    required this.location,
    required this.destinations,
    this.showRecordAction = false,
  });
  final Widget child;
  final String location;
  final List<NavigationDestination> destinations;
  final bool showRecordAction;

  @override
  Widget build(BuildContext context) {
    final paths = destinations
        .map(
          (e) => switch (e.label) {
            'Home' => '/home',
            'Tasks' || 'My Tasks' => '/tasks',
            'Reports' => '/reports',
            'Messages' => '/messages',
            'Profile' => '/profile',
            'Reviews' => '/reviews',
            'Documents' => '/documents',
            'Issues' => '/issues',
            'Projects' => '/projects',
            'Evidence' => '/evidence',
            _ => '/home',
          },
        )
        .toList();
    var selected = paths.indexWhere((path) => location.startsWith(path));
    if (selected < 0) selected = 0;
    return Scaffold(
      extendBody: true,
      body: SafeArea(top: false, bottom: false, child: child),
      floatingActionButtonLocation: FloatingActionButtonLocation.centerDocked,
      floatingActionButton: showRecordAction
          ? Semantics(
              label: 'Record field update',
              button: true,
              child: FloatingActionButton(
                tooltip: 'Record Update',
                onPressed: () => context.push('/voice'),
                backgroundColor: AppColors.bronze,
                foregroundColor: Colors.white,
                elevation: 7,
                shape: const CircleBorder(
                  side: BorderSide(color: Colors.white, width: 4),
                ),
                child: const Icon(Icons.mic_rounded, size: 27),
              ),
            )
          : null,
      bottomNavigationBar: SafeArea(
        top: false,
        child: ClipRRect(
          borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
          child: NavigationBar(
            selectedIndex: selected,
            destinations: destinations,
            onDestinationSelected: (index) => context.go(paths[index]),
          ),
        ),
      ),
    );
  }
}
