"""Optional connection key recovery using the host's OpenSSL."""
import base64
import os
import subprocess

from fastapi import HTTPException

ENV_KEY = 'CORE_AI_CONNECTION_REVEAL_KEY'


def configured():
    return bool(os.environ.get(ENV_KEY)) and os.access('/usr/bin/openssl', os.X_OK)


def transform(value, *, decrypt=False):
    if not configured():
        raise HTTPException(503, 'Encrypted key storage is unavailable on this workstation.')
    try:
        material = base64.b64decode(os.environ[ENV_KEY], validate=True)
        fd = os.memfd_create('core-ai-connection-storage')
        try:
            with os.fdopen(os.dup(fd), 'wb') as output:
                output.write(material)
            os.lseek(fd, 0, os.SEEK_SET)
            command = [
                '/usr/bin/openssl', 'pkeyutl', '-decrypt' if decrypt else '-encrypt',
                '-inkey', f'/proc/self/fd/{fd}', '-pkeyopt', 'rsa_padding_mode:oaep',
                '-pkeyopt', 'rsa_oaep_md:sha256', '-pkeyopt', 'rsa_mgf1_md:sha256',
            ]
            return subprocess.run(command, input=value, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  pass_fds=(fd,), check=True, timeout=5, env={'PATH':'/usr/bin'}).stdout
        finally:
            os.close(fd)
    except (ValueError, OSError, subprocess.SubprocessError):
        raise HTTPException(503, 'Encrypted key storage is unavailable. Check the workstation configuration.') from None
