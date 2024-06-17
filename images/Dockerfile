FROM registry.ci.openshift.org/origin/4.16:cli as cli

FROM centos:stream9
LABEL maintainer="brawilli@redhat.com"

COPY --from=cli /usr/bin/oc /usr/bin/

ADD . /openshift-client-python

RUN yum install -y python3 python3-pip git diffutils && python3 -m pip install --upgrade pip && python3 -m pip install -r /openshift-client-python/requirements.txt

ENV PYTHONPATH=/openshift-client-python/packages:$PYTHONPATH PYTHONUNBUFFERED=1

WORKDIR /openshift-client-python

ENTRYPOINT ["/usr/bin/bash"]
