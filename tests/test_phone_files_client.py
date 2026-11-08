import base64,unittest
from phone_files_client import parse_get_response
from phone_files.v1.get_pb2 import FilesGetResponse

PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jFz8AAAAASUVORK5CYII=')

class NativeThumbnailTests(unittest.TestCase):
    def response(self,outer=1,nested=0):
        result=FilesGetResponse(status=outer)
        result.thumbnail_response.thumbnail=PNG
        result.thumbnail_response.metadata.uri='test://image'
        result.thumbnail_response.status=nested
        return result.SerializeToString()
    def test_native_success_leaves_nested_status_unspecified(self):
        result=parse_get_response(self.response())
        self.assertEqual(result['status'],'ok')
        self.assertTrue(result['data_url'].startswith('data:image/png;base64,'))
    def test_explicit_nested_failure_is_not_overridden(self):
        result=parse_get_response(self.response(nested=3))
        self.assertEqual(result['status'],'not_found')
        self.assertNotIn('data_url',result)
    def test_outer_failure_is_not_overridden(self):
        result=parse_get_response(self.response(outer=2,nested=1))
        self.assertEqual(result['status'],'need_permissions')
        self.assertNotIn('data_url',result)
    def test_native_success_requires_valid_raster_bytes(self):
        body=FilesGetResponse.FromString(self.response())
        body.thumbnail_response.thumbnail=b'not an image'
        with self.assertRaises(ValueError):parse_get_response(body.SerializeToString())
