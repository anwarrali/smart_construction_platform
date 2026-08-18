import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/dependency_injection.dart';
import '../../core/auth/session_manager.dart';
import '../../core/network/network_exceptions.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_radius.dart';
import '../../core/widgets/async_views.dart';
import '../../core/widgets/entity_actions.dart';
import '../../models/chat_message.dart';
import '../projects/project_context_view_model.dart';
import '../../core/l10n/l10n_formats.dart';
import '../../core/l10n/l10n_labels.dart';

class ConversationScreen extends ConsumerStatefulWidget {
  const ConversationScreen({
    super.key,
    this.conversationId,
    this.conversation,
    this.contextType,
    this.contextId,
  });
  final String? conversationId;
  final ProjectConversation? conversation;
  final String? contextType;
  final String? contextId;
  @override
  ConsumerState<ConversationScreen> createState() => _ConversationScreenState();
}

class _ConversationScreenState extends ConsumerState<ConversationScreen> {
  final _content = TextEditingController();
  final _scroll = ScrollController();
  ProjectConversation? _conversation;
  Timer? _poller;
  bool _loading = true;
  bool _sending = false;
  Object? _error;

  @override
  void initState() {
    super.initState();
    _conversation = widget.conversation;
    Future.microtask(_load);
    _poller = Timer.periodic(const Duration(seconds: 15), (_) => _load(quiet: true));
  }

  @override
  void dispose() {
    _poller?.cancel();
    _content.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _load({bool quiet = false}) async {
    final project = ref.read(projectContextProvider).selected;
    if (project == null) return;
    if (!quiet && mounted) setState(() { _loading = true; _error = null; });
    try {
      final value = widget.conversationId != null
          ? await ref.read(messageRepositoryProvider).conversation(widget.conversationId!)
          : await ref.read(messageRepositoryProvider).context(
              project.id, widget.contextType!, widget.contextId!,
            );
      if (value != null && value.unreadCount > 0) {
        await ref.read(messageRepositoryProvider).markRead(value.id);
      }
      if (mounted) {
        setState(() { _conversation = value; _loading = false; });
        _scrollBottom();
      }
    } on NetworkException catch (error) {
      if (!quiet && mounted) setState(() { _error = error; _loading = false; });
    }
  }

  Future<void> _send() async {
    final project = ref.read(projectContextProvider).selected;
    final text = _content.text.trim();
    if (project == null || text.isEmpty || _sending) return;
    setState(() => _sending = true);
    try {
      if (_conversation == null) {
        _conversation = await ref.read(messageRepositoryProvider).createContext(
          projectId: project.id, type: widget.contextType!,
          contextId: widget.contextId!, content: text,
        );
      } else {
        await ref.read(messageRepositoryProvider).send(_conversation!.id, text);
      }
      _content.clear();
      await _load(quiet: true);
    } on NetworkException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(context.l10n.describeError(error))),
        );
      }
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  void _scrollBottom() => WidgetsBinding.instance.addPostFrameCallback((_) {
    if (_scroll.hasClients) {
      _scroll.animateTo(_scroll.position.maxScrollExtent,
          duration: const Duration(milliseconds: 200), curve: Curves.easeOut);
    }
  });

  String _titleFor(BuildContext context) {
    if (_conversation?.title?.isNotEmpty == true) return _conversation!.title!;
    // An entity thread is named after the entity: "Task Discussion" in
    // English, the Arabic equivalent in Arabic. The entity *type* is a known
    // enum, so it is translated; nothing user-written is.
    if (widget.contextType != null) {
      return context.l10n.conversationContextTitle(
        context.l10n.entityLabel(widget.contextType),
      );
    }
    final current = ref.read(sessionProvider).user?.id;
    final names = _conversation?.participants
        .where((item) => item.userId != current)
        .map((item) => item.user.fullName).join(', ');
    return names?.isNotEmpty == true
        ? names!
        : context.l10n.conversationTitle;
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      leading: IconButton(icon: const Icon(Icons.arrow_back), onPressed: () => context.pop()),
      title: Text(
        _titleFor(context),
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
      ),
    ),
    body: SafeArea(
      top: false,
      child: Column(children: [
        Expanded(child: _body()),
        Padding(
          padding: EdgeInsets.fromLTRB(10, 8, 10, 8 + MediaQuery.paddingOf(context).bottom),
          child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
            Expanded(child: TextField(
              controller: _content, minLines: 1, maxLines: 4, maxLength: 4000,
              buildCounter: (_, {required currentLength, required isFocused, maxLength}) => null,
              decoration: InputDecoration(
                hintText: context.l10n.conversationWriteMessage,
              ),
            )),
            const SizedBox(width: 8),
            IconButton.filled(
              onPressed: _sending ? null : _send,
              icon: _sending
                  ? const SizedBox.square(dimension: 18, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.send),
            ),
          ]),
        ),
      ]),
    ),
  );

  Widget _body() {
    if (_loading) {
      return LoadingView(label: context.l10n.conversationLoading);
    }
    if (_error != null) {
      return MessageView(
        icon: Icons.cloud_off,
        title: context.l10n.commonUnavailable(
          context.l10n.conversationTitleShort,
        ),
        message: context.l10n.describeError(_error), onAction: _load,
      );
    }
    final messages = _conversation?.messages ?? const <ChatMessage>[];
    if (messages.isEmpty) {
      return MessageView(
        icon: Icons.forum_outlined,
        title: context.l10n.conversationStartTitle,
        message: context.l10n.conversationStartBody,
      );
    }
    final currentId = ref.read(sessionProvider).user?.id;
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView.builder(
        controller: _scroll,
        padding: const EdgeInsets.all(14),
        itemCount: messages.length,
        itemBuilder: (context, index) {
          final message = messages[index];
          final mine = message.senderId == currentId;
          void forward() => showForwardMessage(
            context: context,
            message: message,
          );
          return GestureDetector(
            // Forwarding is reachable from the message itself rather than
            // from a button on every bubble. Long press is the convention;
            // tap is bound to the same thing because a bubble has no other
            // tap meaning here, and a feature nobody can find is not shipped.
            onTap: forward,
            onLongPress: forward,
            child: Align(
            // Directional alignment: my own messages sit on the trailing
            // edge, which is the right in English and the left in Arabic.
            alignment: mine
                ? AlignmentDirectional.centerEnd
                : AlignmentDirectional.centerStart,
            child: Container(
              constraints: BoxConstraints(maxWidth: MediaQuery.sizeOf(context).width * .82),
              margin: const EdgeInsets.only(bottom: 9),
              padding: const EdgeInsets.all(11),
              decoration: BoxDecoration(
                color: mine ? AppColors.primary : AppColors.card,
                borderRadius: BorderRadius.circular(AppRadius.panel),
                border: mine ? null : Border.all(color: AppColors.border),
              ),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                if (!mine) Text(message.sender.fullName,
                    style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700)),
                // A forwarded message must never read as if the forwarder
                // wrote the original: the quoted block names the true
                // original sender, which the server resolves to the root of
                // the chain even after several hops.
                if (message.forwardOrigin != null)
                  _QuotedOrigin(origin: message.forwardOrigin!, onDark: mine),
                Text(message.content, style: TextStyle(color: mine ? Colors.white : null)),
                // A shared entity carries a label so the recipient can see
                // what kind of record this is about at a glance.
                if (message.isEntityShare)
                  Padding(
                    padding: const EdgeInsets.only(top: 6),
                    child: _SharedEntityChip(
                      entityType: message.sharedEntityType!,
                      onDark: mine,
                    ),
                  ),
                const SizedBox(height: 3),
                // Was `DateFormat.jm()` with no locale, so an Arabic session
                // got an English clock. `formatTime` takes the locale from
                // the tree and applies the app's digit policy.
                Text(context.formatTime(message.createdAt),
                    style: TextStyle(
                        fontSize: 9,
                        color: mine ? Colors.white70 : AppColors.mutedForeground)),
              ]),
              ),
            ),
          );
        },
      ),
    );
  }
}


/// The quoted original inside a forwarded message.
class _QuotedOrigin extends StatelessWidget {
  const _QuotedOrigin({required this.origin, required this.onDark});
  final ForwardOrigin origin;
  final bool onDark;

  @override
  Widget build(BuildContext context) {
    final tint = onDark ? Colors.white : AppColors.accent;
    return Container(
      margin: const EdgeInsets.only(top: 4, bottom: 6),
      padding: const EdgeInsetsDirectional.only(start: 8, top: 5, bottom: 5, end: 6),
      decoration: BoxDecoration(
        color: onDark
            ? Colors.white.withValues(alpha: 0.10)
            : AppColors.muted,
        // A leading rule rather than a full box: the web uses the same
        // quote device, and `BorderDirectional` mirrors it under RTL.
        border: BorderDirectional(
          start: BorderSide(color: tint.withValues(alpha: 0.55), width: 2),
        ),
        borderRadius: BorderRadius.circular(AppRadius.chip),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.shortcut_rounded, size: 11, color: tint),
              const SizedBox(width: 4),
              Flexible(
                child: Text(
                  // The label is translated; the sender's name and the
                  // quoted content below it never are.
                  context.l10n.communicationForwardedFrom(
                    origin.sender.fullName,
                  ),
                  style: TextStyle(
                    fontSize: 10.5,
                    fontWeight: FontWeight.w700,
                    color: tint,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
          const SizedBox(height: 2),
          Text(
            origin.content,
            maxLines: 3,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: 12,
              color: onDark ? Colors.white70 : AppColors.mutedForeground,
            ),
          ),
        ],
      ),
    );
  }
}

/// Labels which kind of project record a shared message is about.
class _SharedEntityChip extends StatelessWidget {
  const _SharedEntityChip({required this.entityType, required this.onDark});
  final String entityType;
  final bool onDark;

  /// Only the icon is fixed per entity type; the wording comes from the
  /// shared `entityLabel` table so a shared issue is called the same thing
  /// here, in a conversation title, and anywhere else it is named.
  static const _icons = <String, IconData>{
    'ISSUE': Icons.report_problem_outlined,
    'TASK': Icons.checklist_rounded,
    'SITE_REPORT': Icons.description_outlined,
    'DESIGN_CHANGE': Icons.architecture_rounded,
    'DOCUMENT': Icons.folder_open_rounded,
  };

  @override
  Widget build(BuildContext context) {
    final label = context.l10n.entityLabel(entityType);
    final icon = _icons[entityType] ?? Icons.link_rounded;
    final tint = onDark ? Colors.white : AppColors.accent;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: onDark ? Colors.white.withValues(alpha: 0.12) : AppColors.accentWash,
        borderRadius: BorderRadius.circular(AppRadius.chip),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 11, color: tint),
          const SizedBox(width: 4),
          Text(
            label,
            style: TextStyle(
              fontSize: 10.5,
              fontWeight: FontWeight.w700,
              color: tint,
            ),
          ),
        ],
      ),
    );
  }
}
