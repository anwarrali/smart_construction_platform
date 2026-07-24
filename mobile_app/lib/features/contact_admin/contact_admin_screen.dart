import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../app/dependency_injection.dart';
import '../../core/widgets/async_views.dart';

class ContactAdminScreen extends ConsumerWidget {
  const ContactAdminScreen({super.key});
  @override
  Widget build(BuildContext context, WidgetRef ref) => Scaffold(
    appBar: AppBar(title: const Text('Contact Administrator')),
    body: FutureBuilder<Map<String, dynamic>>(
      future: ref.read(projectRepositoryProvider).company(),
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const LoadingView();
        }
        final data = snapshot.data;
        if (snapshot.hasError || data == null) {
          return const MessageView(
            icon: Icons.support_agent,
            title: 'Support details unavailable',
            message:
                'Please contact your project office or try again when connected.',
          );
        }
        return ListView(
          padding: const EdgeInsets.all(20),
          children: [
            Text(
              data['name'] as String? ?? 'Company support',
              style: Theme.of(
                context,
              ).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 8),
            Text(
              data['description'] as String? ??
                  'Contact the administrator for account access and support.',
            ),
            const SizedBox(height: 24),
            if (data['phone'] != null)
              ListTile(
                leading: const Icon(Icons.phone_outlined),
                title: const Text('Support phone'),
                subtitle: Text('${data['phone']}'),
              ),
            if (data['email'] != null)
              ListTile(
                leading: const Icon(Icons.email_outlined),
                title: const Text('Support email'),
                subtitle: Text('${data['email']}'),
              ),
            if (data['address'] != null)
              ListTile(
                leading: const Icon(Icons.location_on_outlined),
                title: const Text('Office'),
                subtitle: Text('${data['address']}'),
              ),
          ],
        );
      },
    ),
  );
}
