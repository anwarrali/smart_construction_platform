import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app/app.dart';
import 'app/dependency_injection.dart';
//TEST
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final dependencies = await AppDependencies.create();
  runApp(
    ProviderScope(
      overrides: dependencies.overrides,
      child: const ConstructionFieldApp(),
    ),
  );
}
