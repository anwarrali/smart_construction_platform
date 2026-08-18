import 'package:flutter/material.dart';

import '../theme/app_colors.dart';
import '../theme/app_motion.dart';
import '../theme/app_radius.dart';

/// One bottom-navigation destination: where it goes, and how it is drawn.
///
/// The route used to be recovered by switching on the destination's *label*
/// ('Tasks' -> '/tasks'). That silently ties navigation to English copy, so
/// the first translated label would have sent every tab to the fallback
/// route. The path is data, and the label is a function of the active locale.
class ShellDestination {
  const ShellDestination({
    required this.path,
    required this.icon,
    required this.label,
    this.selectedIcon,
  });

  final String path;
  final IconData icon;
  final IconData? selectedIcon;

  /// Resolved per build, so switching language re-labels the bar without
  /// rebuilding the router.
  final String Function(BuildContext) label;
}

/// The raised action that sits in the middle of the bar.
///
/// Reserved for the one thing a person standing on site reaches for without
/// looking — voice capture. It is a slot in the bar rather than a docked
/// [FloatingActionButton] so it cannot overlap the destinations, cannot
/// collide with a screen's own FAB, and cannot notch the surface.
class NavCenterAction {
  const NavCenterAction({
    required this.icon,
    required this.label,
    required this.onPressed,
  });

  final IconData icon;
  final String label;
  final VoidCallback onPressed;
}

/// The Struct IQ bottom navigation.
///
/// Deliberately not a Material [NavigationBar]. Three things the default
/// cannot do that this product needs:
///
///   * **The surface is navy.** The web states the identity on one constant
///     dark edge (the rail); on a phone that edge is the bottom bar. A white
///     Material bar made the app read as a generic template.
///   * **The active mark travels.** A pill that slides from the old
///     destination to the new one says "you moved" in a way a cross-fading
///     indicator does not. It is one 220ms move on the standard curve — the
///     only motion in the bar.
///   * **The centre slot is an action, not a destination.** Voice is the
///     fastest thing a person can do with gloves on, and it belongs where the
///     thumb already is.
///
/// Everything positional is directional ([PositionedDirectional], a
/// [Directionality]-aware [Row]), so the whole bar — including the travelling
/// indicator — mirrors correctly in Arabic without a single `if (isRtl)`.
class StructNavBar extends StatelessWidget {
  const StructNavBar({
    super.key,
    required this.destinations,
    required this.selectedIndex,
    required this.onSelected,
    this.centerAction,
  });

  final List<ShellDestination> destinations;

  /// The current destination, or a negative value when the visible screen is
  /// reachable from the shell but is not itself a destination (Profile, for
  /// example). Nothing is then marked selected and the indicator is hidden,
  /// which is honest — highlighting Home while Profile is open is not.
  final int selectedIndex;

  final ValueChanged<int> onSelected;
  final NavCenterAction? centerAction;

  /// Where the raised action sits among the destinations.
  int get _centerSlot => destinations.length ~/ 2;

  /// Total slots across the bar, including the centre action if present.
  int get _slotCount => destinations.length + (centerAction == null ? 0 : 1);

  /// A destination's index translated into a visual slot, stepping over the
  /// centre action.
  int _slotOf(int index) =>
      centerAction == null || index < _centerSlot ? index : index + 1;

  static const double _barHeight = 62;
  static const double _indicatorWidth = 46;
  static const double _indicatorHeight = 30;

  @override
  Widget build(BuildContext context) {
    // The bar is the ground under the content, not something to float over a
    // keyboard: when one is open the destinations are unreachable anyway and
    // the bar would eat a third of what is left of the screen.
    if (MediaQuery.viewInsetsOf(context).bottom > 0) {
      return const SizedBox.shrink();
    }

    final children = <Widget>[];
    for (var index = 0; index < destinations.length; index++) {
      if (centerAction != null && index == _centerSlot) {
        children.add(Expanded(child: _CenterAction(action: centerAction!)));
      }
      children.add(
        Expanded(
          child: _DestinationSlot(
            destination: destinations[index],
            selected: index == selectedIndex,
            onTap: () => onSelected(index),
          ),
        ),
      );
    }
    if (centerAction != null && _centerSlot == destinations.length) {
      children.add(Expanded(child: _CenterAction(action: centerAction!)));
    }

    return Container(
      decoration: const BoxDecoration(
        color: AppColors.navSurface,
        border: Border(top: BorderSide(color: AppColors.navBorder)),
      ),
      // The gesture inset is padding *inside* the navy surface, so the strip
      // below the bar is the bar's own colour and page content never shows
      // through it.
      child: SafeArea(
        top: false,
        child: SizedBox(
          height: _barHeight,
          child: LayoutBuilder(
            builder: (context, constraints) {
              final slotWidth = constraints.maxWidth / _slotCount;
              // With nothing selected the indicator stays where it was and
              // fades out, rather than sliding to a destination the user is
              // not on.
              final slot = _slotOf(selectedIndex < 0 ? 0 : selectedIndex);
              return Stack(
                children: [
                  AnimatedPositionedDirectional(
                    duration: AppMotion.fast,
                    curve: AppMotion.standard,
                    start:
                        slot * slotWidth + (slotWidth - _indicatorWidth) / 2,
                    top: 6,
                    width: _indicatorWidth,
                    height: _indicatorHeight,
                    child: AnimatedOpacity(
                      duration: AppMotion.fast,
                      curve: AppMotion.fade,
                      opacity: selectedIndex < 0 ? 0 : 1,
                      child: DecoratedBox(
                        decoration: BoxDecoration(
                          color: AppColors.navMark.withValues(alpha: .18),
                          borderRadius:
                              BorderRadius.circular(AppRadius.control),
                        ),
                      ),
                    ),
                  ),
                  Row(children: children),
                ],
              );
            },
          ),
        ),
      ),
    );
  }
}

class _DestinationSlot extends StatelessWidget {
  const _DestinationSlot({
    required this.destination,
    required this.selected,
    required this.onTap,
  });

  final ShellDestination destination;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final label = destination.label(context);
    final tint = selected ? AppColors.navMark : AppColors.navForeground;
    return Semantics(
      button: true,
      selected: selected,
      label: label,
      child: InkWell(
        onTap: onTap,
        // The whole slot is the target, so the touch area is the full bar
        // height rather than the icon's own bounds.
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              selected ? (destination.selectedIcon ?? destination.icon)
                  : destination.icon,
              size: 22,
              color: tint,
            ),
            const SizedBox(height: 4),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 2),
              child: Text(
                label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                textAlign: TextAlign.center,
                // Announced by the Semantics wrapper above; repeating it here
                // makes a screen reader read every label twice.
                semanticsLabel: '',
                style: TextStyle(
                  fontSize: 10.5,
                  height: 1.1,
                  fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
                  color: selected ? Colors.white : AppColors.navForeground,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _CenterAction extends StatelessWidget {
  const _CenterAction({required this.action});
  final NavCenterAction action;

  @override
  Widget build(BuildContext context) => Semantics(
    button: true,
    label: action.label,
    child: Tooltip(
      message: action.label,
      child: Center(
        child: InkResponse(
          onTap: action.onPressed,
          radius: 30,
          child: Container(
            width: 48,
            height: 48,
            decoration: BoxDecoration(
              color: AppColors.accent,
              shape: BoxShape.circle,
              boxShadow: [
                BoxShadow(
                  color: AppColors.accent.withValues(alpha: .35),
                  blurRadius: 14,
                  offset: const Offset(0, 4),
                ),
              ],
            ),
            child: Icon(action.icon, color: Colors.white, size: 24),
          ),
        ),
      ),
    ),
  );
}
