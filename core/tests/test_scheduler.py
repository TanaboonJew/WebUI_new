from django.test import TestCase
from django.utils import timezone
from unittest.mock import patch
from datetime import timedelta

from users.models import CustomUser
from core.models import DockerContainer, ContainerSchedule
from core.scheduler import reload_schedules
from core.scheduler import scheduler, reload_schedules
from core.jobs import control_container



class SchedulerTestCase(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='doctoral_user', password='secure', role='doctoral', role_verified=True
        )
        self.container = DockerContainer.objects.create(
            user=self.user,
            container_id='test_container_id',
            image_name='test_image',
            status='stopped'
        )

    def test_schedule_creates_jobs(self):
        now = timezone.now()

        ContainerSchedule.objects.create(
            container=self.container,
            start_datetime=now + timedelta(minutes=1),
            end_datetime=now + timedelta(minutes=2),
            active=True,
        )

        reload_schedules()
        jobs = scheduler.get_jobs()

        self.assertEqual(len(jobs), 2)
        self.assertTrue(any('start' in job.id for job in jobs))
        self.assertTrue(any('stop' in job.id for job in jobs))

    @patch('core.jobs.from_env')
    def test_control_container_start(self, mock_from_env):
        mock_client = mock_from_env.return_value
        mock_container = mock_client.containers.get.return_value
        mock_container.status = 'created'

        control_container('test_container_id', 'start')
        mock_container.start.assert_called_once()

    @patch('core.jobs.from_env')
    def test_control_container_stop(self, mock_from_env):
        mock_client = mock_from_env.return_value
        mock_container = mock_client.containers.get.return_value
        mock_container.status = 'running'

        control_container('test_container_id', 'stop')
        mock_container.stop.assert_called_once()

    def tearDown(self):
        scheduler.remove_all_jobs()
