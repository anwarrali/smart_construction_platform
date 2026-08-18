import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/dependency_injection.dart';
import '../../features/projects/project_context_view_model.dart';
import '../../l10n/app_localizations.dart';
import '../../models/chat_message.dart';
import '../../models/user.dart';
import '../auth/session_manager.dart';
import '../l10n/l10n_labels.dart';
import '../theme/app_colors.dart';
import '../theme/app_radius.dart';
import '../theme/app_spacing.dart';
import 'async_views.dart';

/// What a person is doing when they send a record to a colleague.
///
/// All three run through the same authorized endpoint — the server is
/// explicit that sharing an entity only ever writes a Message and never
/// touches the entity's owner, assignee, status or verification state. The
/// distinction is therefore **wording and intent**, and it matters: calling a
/// consultation "Forward" tells a Consultant they now own a task they do not.
enum ShareIntent {
  /// Send this on to somebody else.
  forward,

  /// Ask a colleague to advise. Nothing changes hands.
  askOpinion,

  /// Send a copy into a conversation.
  share;

  String label(AppL10n l10n) => switch (this) {
    ShareIntent.forward => l10n.shareForward,
    ShareIntent.askOpinion => l10n.shareAskOpinion,
    ShareIntent.share => l10n.shareShare,
  };

  String hint(AppL10n l10n) => switch (this) {
    ShareIntent.forward => l10n.shareForwardHint,
    ShareIntent.askOpinion => l10n.shareAskOpinionHint,
    ShareIntent.share => l10n.shareShareHint,
  };

  IconData get icon => switch (this) {
    ShareIntent.forward => Icons.shortcut_rounded,
    ShareIntent.askOpinion => Icons.help_outline_rounded,
    ShareIntent.share => Icons.ios_share_rounded,
  };

  String success(AppL10n l10n) => switch (this) {
    ShareIntent.forward => l10n.shareSentForward,
    ShareIntent.askOpinion => l10n.shareSentOpinion,
    ShareIntent.share => l10n.shareSentShare,
  };
}

/// The actions a given kind of record offers, as specified by the product:
///
///   * Issue, Design Change — Forward and Ask for Opinion
///   * Task — Ask for Opinion only (a task is never "forwarded"; reassignment
///     is a different operation with different consequences)
///   * Site Report, Document — Share
///
/// Formal verification of a site report by the Project Manager is a separate
/// workflow and is deliberately not in this list.
List<ShareIntent> intentsForEntity(String entityType) =>
    switch (entityType.toUpperCase()) {
      'ISSUE' || 'DESIGN_CHANGE' => const [
        ShareIntent.forward,
        ShareIntent.askOpinion,
      ],
      'TASK' => const [ShareIntent.askOpinion],
      'SITE_REPORT' || 'DOCUMENT' => const [ShareIntent.share],
      _ => const [],
    };

/// Opens the contextual action sheet for a record.
///
/// A sheet rather than a row of buttons on every card: the brief is explicit
/// that ten buttons per card is not the answer, and this keeps the list dense
/// while still making the actions findable from the record itself.
Future<void> showEntityActions({
  required BuildContext context,
  required String entityType,
  required String entityId,
  String? entityTitle,
}) async {
  final intents = intentsForEntity(entityType);
  if (intents.isEmpty) return;
  final l10n = context.l10n;
  final chosen = await showModalBottomSheet<ShareIntent>(
    context: context,
    useSafeArea: true,
    builder: (sheetContext) => SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.page,
              0,
              AppSpacing.page,
              AppSpacing.xs,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  entityTitle?.trim().isNotEmpty == true
                      ? entityTitle!.trim()
                      : l10n.shareActionsTitle,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(sheetContext).textTheme.titleLarge,
                ),
                const SizedBox(height: 2),
                Text(
                  l10n.entityLabel(entityType),
                  style: Theme.of(sheetContext).textTheme.bodySmall,
                ),
              ],
            ),
          ),
          const Divider(),
          for (final intent in intents)
            ListTile(
              leading: Icon(intent.icon, color: AppColors.accent),
              title: Text(
                intent.label(l10n),
                style: const TextStyle(fontWeight: FontWeight.w700),
              ),
              subtitle: Text(intent.hint(l10n)),
              onTap: () => Navigator.pop(sheetContext, intent),
            ),
          const SizedBox(height: AppSpacing.sm),
        ],
      ),
    ),
  );
  if (chosen == null || !context.mounted) return;
  await showShareSheet(
    context: context,
    intent: chosen,
    entityType: entityType,
    entityId: entityId,
  );
}

/// Opens the recipient picker and performs the share/forward.
///
/// Exactly one of [entityType]/[entityId] and [messageId] is used: an entity
/// goes through `POST /messages/share`, a message through
/// `POST /messages/{id}/forward`.
Future<void> showShareSheet({
  required BuildContext context,
  required ShareIntent intent,
  String? entityType,
  String? entityId,
  String? messageId,
}) async {
  assert(
    (entityType != null && entityId != null) || messageId != null,
    'share needs either an entity or a message',
  );
  await showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    builder: (_) => _ShareSheet(
      intent: intent,
      entityType: entityType,
      entityId: entityId,
      messageId: messageId,
    ),
  );
}

/// The Forward action offered on a message in a conversation.
Future<void> showForwardMessage({
  required BuildContext context,
  required ChatMessage message,
}) => showShareSheet(
  context: context,
  intent: ShareIntent.forward,
  messageId: message.id,
);

class _ShareSheet extends ConsumerStatefulWidget {
  const _ShareSheet({
    required this.intent,
    this.entityType,
    this.entityId,
    this.messageId,
  });

  final ShareIntent intent;
  final String? entityType;
  final String? entityId;
  final String? messageId;

  @override
  ConsumerState<_ShareSheet> createState() => _ShareSheetState();
}

class _ShareSheetState extends ConsumerState<_ShareSheet> {
  final _note = TextEditingController();
  final _filter = TextEditingController();
  final _selected = <String>{};

  List<User> _people = const [];
  bool _loading = true;
  bool _sending = false;
  Object? _error;

  @override
  void initState() {
    super.initState();
    if (widget.intent == ShareIntent.askOpinion) {
      // A consultation that arrives with no question is just a copy of a
      // record. The prompt is editable; it only has to not be empty.
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _note.text.isEmpty) {
          _note.text = context.l10n.shareOpinionPrefill;
        }
      });
    }
    Future.microtask(_load);
  }

  @override
  void dispose() {
    _note.dispose();
    _filter.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final project = ref.read(projectContextProvider).selected;
    if (project == null) {
      if (mounted) setState(() => _loading = false);
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final options = await ref
          .read(messageRepositoryProvider)
          .recipientOptions(project.id);
      final me = ref.read(sessionProvider).user?.id;
      if (mounted) {
        setState(() {
          _people = options.users
              .where((person) => person.id != me)
              .toList();
          _loading = false;
        });
      }
    } catch (error) {
      if (mounted) {
        setState(() {
          _error = error;
          _loading = false;
        });
      }
    }
  }

  Future<void> _send() async {
    if (_selected.isEmpty || _sending) return;
    final l10n = context.l10n;
    final messenger = ScaffoldMessenger.of(context);
    final router = GoRouter.of(context);
    setState(() => _sending = true);
    try {
      final repository = ref.read(messageRepositoryProvider);
      final note = _note.text.trim();
      final conversation = widget.messageId != null
          ? await repository.forward(
              messageId: widget.messageId!,
              recipientIds: _selected.toList(),
              note: note.isEmpty ? null : note,
            )
          : await repository.shareEntity(
              entityType: widget.entityType!,
              entityId: widget.entityId!,
              recipientIds: _selected.toList(),
              note: note.isEmpty ? null : note,
            );
      if (!mounted) return;
      Navigator.pop(context);
      messenger.showSnackBar(
        SnackBar(
          content: Text(widget.intent.success(l10n)),
          action: SnackBarAction(
            label: l10n.shareOpen,
            onPressed: () => router.push('/messages/${conversation.id}'),
          ),
        ),
      );
    } catch (error) {
      if (mounted) {
        setState(() => _sending = false);
        messenger.showSnackBar(
          SnackBar(content: Text(l10n.describeError(error))),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final needle = _filter.text.trim().toLowerCase();
    final visible = needle.isEmpty
        ? _people
        : _people
              .where(
                (person) =>
                    person.fullName.toLowerCase().contains(needle) ||
                    l10n.roleLabel(person.role).toLowerCase().contains(needle),
              )
              .toList();

    return Padding(
      // The keyboard inset is the sheet's own padding, so the note field and
      // the send button stay above it instead of behind it.
      padding: EdgeInsets.only(
        bottom: MediaQuery.viewInsetsOf(context).bottom,
      ),
      child: DraggableScrollableSheet(
        expand: false,
        initialChildSize: .78,
        minChildSize: .45,
        maxChildSize: .95,
        builder: (context, controller) => Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(
                AppSpacing.page,
                0,
                AppSpacing.page,
                AppSpacing.sm,
              ),
              child: Row(
                children: [
                  Icon(widget.intent.icon, color: AppColors.accent),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      widget.intent.label(l10n),
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                  ),
                ],
              ),
            ),
            Expanded(child: _list(controller, visible)),
            if (!_loading && _error == null && _people.isNotEmpty)
              _footer(l10n),
          ],
        ),
      ),
    );
  }

  Widget _list(ScrollController controller, List<User> visible) {
    final l10n = context.l10n;
    if (_loading) {
      return LoadingView(label: l10n.shareLoadingRecipients);
    }
    if (_error != null) {
      return MessageView(
        icon: Icons.cloud_off_rounded,
        title: l10n.commonUnavailable(l10n.shareRecipients),
        message: l10n.describeError(_error),
        onAction: _load,
      );
    }
    if (_people.isEmpty) {
      return MessageView(
        icon: Icons.group_off_outlined,
        title: l10n.shareNoRecipientsTitle,
        message: l10n.shareNoRecipientsBody,
      );
    }
    return ListView(
      controller: controller,
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.page,
        0,
        AppSpacing.page,
        AppSpacing.sm,
      ),
      children: [
        TextField(
          controller: _filter,
          onChanged: (_) => setState(() {}),
          decoration: InputDecoration(
            isDense: true,
            labelText: l10n.shareRecipients,
            prefixIcon: const Icon(Icons.search_rounded),
          ),
        ),
        const SizedBox(height: AppSpacing.xs),
        for (final person in visible)
          CheckboxListTile(
            dense: true,
            contentPadding: EdgeInsets.zero,
            value: _selected.contains(person.id),
            title: Text(
              person.fullName,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
            subtitle: Text(l10n.roleLabel(person.role)),
            onChanged: (checked) => setState(() {
              if (checked == true) {
                _selected.add(person.id);
              } else {
                _selected.remove(person.id);
              }
            }),
          ),
        const SizedBox(height: AppSpacing.sm),
        TextField(
          controller: _note,
          minLines: 2,
          maxLines: 4,
          maxLength: 4000,
          buildCounter:
              (_, {required currentLength, required isFocused, maxLength}) =>
                  null,
          decoration: InputDecoration(labelText: l10n.shareNoteLabel),
        ),
      ],
    );
  }

  Widget _footer(AppL10n l10n) => Container(
    padding: const EdgeInsets.fromLTRB(
      AppSpacing.page,
      AppSpacing.sm,
      AppSpacing.page,
      AppSpacing.md,
    ),
    decoration: const BoxDecoration(
      color: AppColors.card,
      border: Border(top: BorderSide(color: AppColors.border)),
    ),
    child: Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          _selected.isEmpty
              ? l10n.shareSelectRecipient
              : l10n.shareSelectedCount(_selected.length),
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: AppSpacing.xs),
        FilledButton.icon(
          onPressed: _selected.isEmpty || _sending ? null : _send,
          icon: _sending
              ? const SizedBox.square(
                  dimension: 18,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: Colors.white,
                  ),
                )
              : const Icon(Icons.send_rounded),
          label: Text(_sending ? l10n.shareSending : l10n.shareSend),
          style: FilledButton.styleFrom(
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(AppRadius.control),
            ),
          ),
        ),
      ],
    ),
  );
}
