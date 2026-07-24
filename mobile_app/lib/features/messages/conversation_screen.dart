import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../app/dependency_injection.dart';
import '../../core/auth/session_manager.dart';
import '../../core/network/network_exceptions.dart';
import '../../core/widgets/async_views.dart';
import '../../models/chat_message.dart';
import '../projects/project_context_view_model.dart';

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
  String? _error;

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
      if (!quiet && mounted) setState(() { _error = error.message; _loading = false; });
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
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error.message)));
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

  String get _title {
    if (_conversation?.title?.isNotEmpty == true) return _conversation!.title!;
    if (widget.contextType != null) return '${widget.contextType} Discussion';
    final current = ref.read(sessionProvider).user?.id;
    final names = _conversation?.participants
        .where((item) => item.userId != current)
        .map((item) => item.user.fullName).join(', ');
    return names?.isNotEmpty == true ? names! : 'Project Conversation';
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      leading: IconButton(icon: const Icon(Icons.arrow_back), onPressed: () => context.pop()),
      title: Text(_title, maxLines: 1, overflow: TextOverflow.ellipsis),
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
              decoration: const InputDecoration(hintText: 'Write a project message…'),
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
      return const LoadingView(label: 'Loading conversation');
    }
    if (_error != null) {
      return MessageView(
        icon: Icons.cloud_off, title: 'Conversation unavailable',
        message: _error!, onAction: _load,
      );
    }
    final messages = _conversation?.messages ?? const <ChatMessage>[];
    if (messages.isEmpty) {
      return const MessageView(
        icon: Icons.forum_outlined, title: 'Start the discussion',
        message: 'Send the first contextual project message.',
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
          return Align(
            alignment: mine ? Alignment.centerRight : Alignment.centerLeft,
            child: Container(
              constraints: BoxConstraints(maxWidth: MediaQuery.sizeOf(context).width * .82),
              margin: const EdgeInsets.only(bottom: 9),
              padding: const EdgeInsets.all(11),
              decoration: BoxDecoration(
                color: mine ? Theme.of(context).colorScheme.primary : Colors.white,
                borderRadius: BorderRadius.circular(14),
                border: mine ? null : Border.all(color: Colors.black12),
              ),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                if (!mine) Text(message.sender.fullName,
                    style: const TextStyle(fontSize: 11, fontWeight: FontWeight.bold)),
                Text(message.content, style: TextStyle(color: mine ? Colors.white : null)),
                const SizedBox(height: 3),
                Text(DateFormat.jm().format(message.createdAt),
                    style: TextStyle(fontSize: 9, color: mine ? Colors.white70 : Colors.black45)),
              ]),
            ),
          );
        },
      ),
    );
  }
}
