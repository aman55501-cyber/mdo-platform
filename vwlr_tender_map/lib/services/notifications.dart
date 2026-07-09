import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:timezone/data/latest.dart' as tzdata;
import 'package:timezone/timezone.dart' as tz;
import '../models/tender.dart';

/// Local deadline reminders. Schedules a notification 3 days and 1 day
/// before each open tender's bid deadline.
class Notifications {
  static final _plugin = FlutterLocalNotificationsPlugin();
  static bool _ready = false;

  static Future<void> init() async {
    // flutter_local_notifications has no web implementation; skip so the
    // app runs in a browser (deadline reminders are an Android feature).
    if (kIsWeb || _ready) return;
    tzdata.initializeTimeZones();
    tz.setLocalLocation(tz.getLocation('Asia/Kolkata'));
    const android = AndroidInitializationSettings('@mipmap/ic_launcher');
    await _plugin.initialize(const InitializationSettings(android: android));
    await _plugin
        .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>()
        ?.requestNotificationsPermission();
    _ready = true;
  }

  static const _details = NotificationDetails(
    android: AndroidNotificationDetails(
      'tender_deadlines', 'Tender deadlines',
      channelDescription: 'Reminders before bid submission closes',
      importance: Importance.max, priority: Priority.high,
    ),
  );

  static Future<void> syncFor(List<Tender> tenders) async {
    if (kIsWeb) return;
    await init();
    await _plugin.cancelAll();
    var id = 0;
    for (final t in tenders) {
      if (t.deadline == null) continue;
      if (t.status == TenderStatus.closed ||
          t.status == TenderStatus.won ||
          t.status == TenderStatus.lost) {
        continue;
      }
      for (final lead in [3, 1]) {
        final when = tz.TZDateTime.from(
            t.deadline!.subtract(Duration(days: lead)), tz.local);
        if (when.isBefore(tz.TZDateTime.now(tz.local))) {
          continue;
        }
        await _plugin.zonedSchedule(
          id++,
          '$lead day${lead > 1 ? 's' : ''} to bid: ${t.authority ?? t.title}',
          '${t.title} closes ${_d(t.deadline!)}',
          when,
          _details,
          androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
          uiLocalNotificationDateInterpretation:
              UILocalNotificationDateInterpretation.absoluteTime,
        );
      }
    }
  }

  static String _d(DateTime d) =>
      '${d.day}/${d.month} ${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';
}
