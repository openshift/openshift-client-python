
node('bastion2') {
    stage('repo-setup') {
        sh "rm -rf git"
        dir('git') {
            dir('openshift-client-python') {
                // This will also create the git/openshift-client-python directory
                checkout scm
                env.PYTHONPATH = "${pwd()}/packages"
                ocp_dir = pwd()
            }
        }
    }

    stage('unittests') {
        dir("${ocp_dir}") {
            echo "Running run tests"
            sh "./run_unittests.sh"
        }
    }

}
