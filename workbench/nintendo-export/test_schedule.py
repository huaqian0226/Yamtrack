import datetime,importlib.util,unittest
from pathlib import Path
from zoneinfo import ZoneInfo
spec=importlib.util.spec_from_file_location('runner',Path(__file__).with_name('scheduled-sync.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class ScheduleTest(unittest.TestCase):
 def test_daily_and_catchup(self):
  tz=ZoneInfo('Europe/London')
  for month in [1,7]:
   morning=datetime.datetime(2026,month,20,8,tzinfo=tz)
   self.assertFalse(m.daily_due(morning.replace(hour=7,minute=59),{},100))
   self.assertTrue(m.daily_due(morning,{},100))
   self.assertTrue(m.daily_due(morning.replace(hour=17),{},100))
   self.assertFalse(m.daily_due(morning,{'success_day':morning.date().isoformat()},100))
   self.assertFalse(m.daily_due(morning,{'retry_after':101},100))
if __name__=='__main__':unittest.main()
