import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../app/dependency_injection.dart';
import '../../core/widgets/async_views.dart';
import '../../core/l10n/l10n_labels.dart';

class ContactAdminScreen extends ConsumerWidget {
  const ContactAdminScreen({super.key});
  @override
  Widget build(BuildContext context, WidgetRef ref) => Scaffold(
    appBar: AppBar(title: Text(context.l10n.contactAdminTitle)),
    body: FutureBuilder<Map<String, dynamic>>(
      future: ref.read(projectRepositoryProvider).company(),
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const LoadingView();
        }
        final data = snapshot.data;
        if (snapshot.hasError || data == null) {
          return MessageView(
            icon: Icons.support_agent,
            title: context.l10n.contactAdminUnavailable,
            message: context.l10n.contactAdminUnavailableBody,
          );
        }
        return ListView(
          padding: const EdgeInsets.all(20),
          children: [
            Text(
              data['name'] as String? ??
                  context.l10n.contactAdminCompanySupport,
              style: Theme.of(
                context,
              ).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 8),
            Text(
              data['description'] as String? ??
                  context.l10n.contactAdminBody,
            ),
            const SizedBox(height: 24),
            if (data['phone'] != null)
              ListTile(
                leading: const Icon(Icons.phone_outlined),
                title: Text(context.l10n.contactAdminPhone),
                subtitle: Text('${data['phone']}'),
              ),
            if (data['email'] != null)
              ListTile(
                leading: const Icon(Icons.email_outlined),
                title: Text(context.l10n.contactAdminEmail),
                subtitle: Text('${data['email']}'),
              ),
            if (data['address'] != null)
              ListTile(
                leading: const Icon(Icons.location_on_outlined),
                title: Text(context.l10n.contactAdminOffice),
                subtitle: Text('${data['address']}'),
              ),
          ],
        );
      },
    ),
  );
}
