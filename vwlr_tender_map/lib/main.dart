import 'package:flutter/material.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import 'config.dart';
import 'screens/home_shell.dart';
import 'services/notifications.dart';
import 'theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Supabase.initialize(
    url: Config.supabaseUrl,
    // The configured key is a Supabase publishable key (sb_publishable_...).
    publishableKey: Config.supabaseAnonKey,
  );
  await Notifications.init();
  runApp(const VwlrApp());
}

class VwlrApp extends StatelessWidget {
  const VwlrApp({super.key});
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'VWLR Tender Map',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(),
      home: const HomeShell(),
    );
  }
}
