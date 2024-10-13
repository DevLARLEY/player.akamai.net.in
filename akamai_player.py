import argparse
import base64
import hashlib
import json
import logging
import re

import m3u8
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad


class AkamaiPlayerIN:
    def __init__(
            self,
            token: str,
            course_id: int,
            video_id: int
    ):
        self.token = token
        self.course_id = course_id
        self.video_id = video_id

        self.session = requests.Session()

    def _get_player_token(self):
        response = self.session.get(
            url='https://tempapi.classx.co.in/get/fetchVideoDetailsById',
            params={
                'course_id': self.course_id,
                'video_id': self.video_id,
                'ytflag': '0',
                'folder_wise_course': '0',
            },
            headers={
                'auth-key': 'appxapi',
                'authorization': self.token,
            }
        )
        logging.info(response.status_code)

        return response.json()["data"]["video_player_token"]

    def _get_props(
            self,
            player_token: str
    ):
        response = self.session.get(
            url="https://player.akamai.net.in/secure-player",
            params={
                "token": player_token
            }
        )
        logging.info(response.status_code)

        __NEXT_DATA__ = json.loads(
            re.findall(r"<script id=\"__NEXT_DATA__\" type=\"application/json\">(.*)</script>", response.text)[0]
        )
        props = __NEXT_DATA__["props"]["pageProps"]

        return props["datetime"], props["ivb6"], props["urls"]

    @staticmethod
    def _derive_key(
            datetime: str,
            token: str
    ) -> bytes:
        n = datetime[-4:]
        o = int(n[3])

        s = datetime + token[int(n[0]):int(n[1:3])]

        c = hashlib.sha256()
        c.update(s.encode())
        u = c.digest()

        if o == 6:
            return u[:16]
        elif o == 7:
            return u[:24]
        else:
            return u

    @staticmethod
    def aes_decrypt(
            content: bytes,
            lv: bytes,
            ivb6: bytes
    ) -> str:
        cipher = AES.new(
            lv,
            AES.MODE_CBC,
            ivb6
        )
        decrypted_content = cipher.decrypt(content)

        return unpad(decrypted_content, AES.block_size).decode()

    def get_metadata(self):
        token = self._get_player_token()
        datetime, ivb6, urls = self._get_props(token)
        derived_key = self._derive_key(datetime, token)

        master_playlist = m3u8.M3U8()

        for url in urls:
            kstr = base64.b64decode(player.aes_decrypt(
                content=base64.b64decode(url["kstr"]),
                lv=derived_key,
                ivb6=base64.b64decode(ivb6)
            ))

            key_file = f"{self.course_id}_{self.video_id}_{url['quality']}.key"
            with open(key_file, "wb") as f:
                f.write(kstr)

            jstr = player.aes_decrypt(
                content=base64.b64decode(url["jstr"]),
                lv=derived_key,
                ivb6=base64.b64decode(ivb6)
            )

            m3u8_object = m3u8.loads(jstr)
            m3u8_object.keys[0].uri = key_file

            playlist_file = f"{self.course_id}_{self.video_id}_{url['quality']}.m3u8"
            with open(playlist_file, "w") as f:
                f.write(m3u8_object.dumps())

            master_playlist.add_playlist(
                m3u8.Playlist(
                    stream_info={
                        'bandwidth': 0,
                        'resolution': url["quality"].replace("p", "x" + str(round(int(url["quality"][:-1]) * (16 / 9))))
                    },
                    uri=playlist_file,
                    media="",
                    base_uri=""
                )
            )

        master_file = f"{self.course_id}_{self.video_id}.m3u8"
        master_playlist.dump(master_file)

        return master_file


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", action="store", required=True)
    parser.add_argument("--course", action="store", required=True)
    parser.add_argument("--video", action="store", required=True)
    args = parser.parse_args()

    logging.basicConfig(format='[%(levelname)s]: %(message)s', level=logging.INFO)

    player = AkamaiPlayerIN(
        token=args.token,
        course_id=args.course,
        video_id=args.video,
    )
    logging.info(player.get_metadata())
