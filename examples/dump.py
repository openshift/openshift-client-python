#!/usr/bin/env python

import openshift as oc

if __name__ == '__main__':
    with oc.client_host():
        oc.dumpinfo_core('dumps/', num_combined_journal_entries=50, num_critical_journal_entries=50, logs_since='1h', logs_tail=500)
