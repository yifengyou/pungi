import os
import requests


class MBSWrapper(object):
    def __init__(self, api_url):
        """
        :param string api_url: e.g. https://example.com/module-build-service/2
        """
        self.api_url = api_url

    def _get(self, resource, params=None):
        """Get specified resource.

        :param string resource: e.g. module-builds, final-modulemd
        :param dict data:
        """
        url = os.path.join(self.api_url, resource)
        try:
            resp = requests.get(url, params=params)
        except Exception as e:
            raise Exception(
                "Failed to query URL %s with params %s - %s" % (url, params, str(e))
            )
        resp.raise_for_status()
        return resp

    def module_builds(self, filters=None):
        return self._get("module-builds", filters).json()

    def get_module_build_by_nsvc(self, nsvc):
        nsvc_list = nsvc.split(":")
        if len(nsvc_list) != 4:
            raise ValueError("Invalid N:S:V:C - %s" % nsvc)
        filters = dict(zip(["name", "stream", "version", "context"], nsvc_list))
        resp = self.module_builds(filters)
        if resp["items"]:
            return resp["items"][0]
        else:
            return None

    def final_modulemd(self, module_build_id):
        return self._get("final-modulemd/%s" % module_build_id).json()
