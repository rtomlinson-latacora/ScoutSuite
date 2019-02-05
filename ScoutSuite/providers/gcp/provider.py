# -*- coding: utf-8 -*-[d['value'] for d in l]

import os

import warnings
import google.auth
import googleapiclient
import google.oauth2.service_account
from googleapiclient.discovery import build
from opinel.utils.console import printError, printException

from ScoutSuite.providers.base.provider import BaseProvider
from ScoutSuite.providers.gcp.configs.services import GCPServicesConfig
from ScoutSuite.providers.gcp.utils import gcp_connect_service


class GCPCredentials():

    def __init__(self, api_client_credentials, cloud_client_credentials):
        self.api_client_credentials = api_client_credentials
        self.cloud_client_credentials = cloud_client_credentials

class GCPProvider(BaseProvider):
    """
    Implements provider for GCP
    """

    def __init__(self, project_id=None, folder_id=None, organization_id=None,
                 report_dir=None, timestamp=None, services=None, skipped_services=None, thread_config=4, **kwargs):
        services = [] if services is None else services
        skipped_services = [] if skipped_services is None else skipped_services

        self.profile = 'gcp-profile'  # TODO this is aws-specific

        self.metadata_path = '%s/metadata.json' % os.path.split(os.path.abspath(__file__))[0]

        self.provider_code = 'gcp'
        self.provider_name = 'Google Cloud Platform'

        self.projects = []
        self.project_id = project_id
        self.folder_id = folder_id
        self.organization_id = organization_id

        self.service_account = service_account

        self.services_config = GCPServicesConfig

        super(GCPProvider, self).__init__(report_dir, timestamp, services, skipped_services, thread_config)

    def authenticate(self, key_file=None, user_account=None, service_account=None, **kargs):
        """
        Implement authentication for the GCP provider
        Refer to https://google-auth.readthedocs.io/en/stable/reference/google.auth.html.

        :return:
        """

        if user_account:
            # disable GCP warning about using User Accounts
            warnings.filterwarnings("ignore", "Your application has authenticated using end user credentials")
            pass  # Nothing more to do
        elif service_account: # This is fine for now except we've added a boolean property to the GCPProvider for service_accounts
            client_secrets_path = os.path.abspath(key_file)  # TODO this is probably wrong
            # maybe we should add a flag if using a service_account type
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = client_secrets_path
            # There should be some other differentiating factor but maybe for know its enough to look for a service account credential
            # and a flag to search all projects
            # no project_id which should be fine

            self.service_account = True
        else:
            printError('Failed to authenticate to GCP - no supported account type')
            return False

        try:

            self.credentials, project_id = google.auth.default()

            if self.credentials:

                if self.project_id:
                    # service_account credentials with project_id will follow this path
                    self.projects = self._get_projects(parent_type='project',
                                                       parent_id=self.project_id)
                    self.aws_account_id = self.project_id # FIXME this is for AWS
                    self.profile = self.project_id # FIXME this is for AWS

                elif self.organization_id:
                    self.projects = self._get_projects(parent_type='organization',
                                                       parent_id=self.organization_id)
                    self.aws_account_id = self.organization_id # FIXME this is for AWS
                    self.profile = self.organization_id # FIXME this is for AWS

                elif self.folder_id:
                    self.projects = self._get_projects(parent_type='folder',
                                                       parent_id=self.folder_id)
                    self.aws_account_id = self.folder_id # FIXME this is for AWS
                    self.profile = self.folder_id # FIXME this is for AWS

                elif self.service_account: # We know that project_id hasn't been provided and that we have a service account
                    self.projects = self._get_projects(parent_type='service-account',
                                                       parent_id=self.project_id,
                                                       service_account=self.service_account)
                    self.aws_account_id = "gcp-audit-service-account" # FIXME this is for AWS
                    self.profile = "gcp-audit-service-account" # FIXME this is for AWS

                else:
                    # FIXME this will fail if no default project is set in gcloud config
                    # This is caused because html.py is looking for a profile to build the report
                    self.project_id = project_id
                    self.projects = self._get_projects(parent_type='project',
                                                       parent_id=self.project_id)
                    self.aws_account_id = self.project_id # FIXME this is for AWS
                    self.profile = self.project_id # FIXME this is for AWS

                # TODO this shouldn't be done here? but it has to in order to init with projects...
                self.services.set_projects(projects=self.projects)

                return True
            else:
                return False

        except google.auth.exceptions.DefaultCredentialsError as e:
            printError('Failed to authenticate to GCP')
            printException(e)
            return False

        except googleapiclient.errors.HttpError as e:
            printError('Failed to authenticate to GCP')
            printException(e)
            return False


    def preprocessing(self, ip_ranges=None, ip_ranges_name_key=None):
        """
        TODO description
        Tweak the AWS config to match cross-resources and clean any fetching artifacts

        :param ip_ranges:
        :param ip_ranges_name_key:
        :return: None
        """
        ip_ranges = [] if ip_ranges is None else ip_ranges

        self._match_instances_and_snapshots()
        self._match_networks_and_instances()

        super(GCPProvider, self).preprocessing()

    def _get_projects(self, parent_type, parent_id, service_account=False):
        """
        Returns all the projects in a given organization or folder. For a project_id it only returns the project
        details.
        """

        if parent_type not in ['project', 'organization', 'folder', 'service-account']:
            return None

        projects = []

        #FIXME can't currently be done with API client library as it consumes v1 which doesn't support folders
        """

        resource_manager_client = resource_manager.Client(credentials=self.credentials)

        project_list = resource_manager_client.list_projects()

        for p in project_list:
            if p.parent['id'] == self.organization_id and p.status == 'ACTIVE':
                projects.append(p.project_id)
        """

        resource_manager_client_v1 = gcp_connect_service(service='cloudresourcemanager', credentials=self.credentials)
        resource_manager_client_v2 = gcp_connect_service(service='cloudresourcemanager-v2', credentials=self.credentials)

        if parent_type == 'project':
            project_response = resource_manager_client_v1.projects().list(filter='id:%s' % parent_id).execute()
            if 'projects' in project_response.keys():
                for project in project_response['projects']:
                    if project['lifecycleState'] == "ACTIVE":
                        projects.append(project)

        elif parent_type == 'service-account':
            project_response = resource_manager_client_v1.projects().list().execute()
            if 'projects' in project_response.keys():
                for project in project_response['projects']:
                    if project['lifecycleState'] == "ACTIVE":
                        projects.append(project)
        else:

            # get parent children projectss
            request = resource_manager_client_v1.projects().list(filter='parent.id:%s' % parent_id)
            while request is not None:
                response = request.execute()

                if 'projects' in response.keys():
                    for project in response['projects']:
                        if project['lifecycleState'] == "ACTIVE":
                            projects.append(project)

                request = resource_manager_client_v1.projects().list_next(previous_request=request,
                                                                          previous_response=response)

            # get parent children projects in children folders recursively
            folder_response = resource_manager_client_v2.folders().list(parent='%ss/%s' % (parent_type, parent_id)).execute()
            if 'folders' in folder_response.keys():
                for folder in folder_response['folders']:
                    projects.extend(self._get_projects("folder", folder['name'].strip(u'folders/')))

        return projects

    def _match_instances_and_snapshots(self):
        """
        Compare Compute Engine instances and snapshots to identify instance disks that do not have a snapshot.

        :return:
        """

        if 'computeengine' in self.services:
            for instance in self.services['computeengine']['instances'].values():
                for instance_disk in instance['disks'].values():
                    instance_disk['snapshots'] = []
                    for disk in self.services['computeengine']['snapshots'].values():
                        if disk['status'] == 'READY' and disk['source_disk_url'] == instance_disk['source_url']:
                            instance_disk['snapshots'].append(disk)

                    instance_disk['latest_snapshot'] = max(instance_disk['snapshots'],
                                                           key=lambda x: x['creation_timestamp']) \
                        if instance_disk['snapshots'] else None


    def _match_networks_and_instances(self):
        """
        For each network, math instances in that network

        :return:
        """

        if 'computeengine' in self.services:
            for network in self.services['computeengine']['networks'].values():
                network['instances'] = []
                for instance in self.services['computeengine']['instances'].values():
                    for network_interface in instance['network_interfaces']:
                        if network_interface['network'] == network['network_url']:
                            network['instances'].append(instance['id'])
