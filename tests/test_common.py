import os

TESTDIR = os.path.dirname(__file__)
RPMDIR = os.path.join(TESTDIR, "rpms")
RPMFILE = {
    'fuse-common':os.path.join(RPMDIR, "fuse-common-3.5.0-1.fc30.x86_64.rpm"),
    'geronimo-jta':os.path.join(RPMDIR, "geronimo-jta-1.1.1-17.el7.noarch.rpm"),
}
