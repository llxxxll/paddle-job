import kubernetes
from kubernetes import client, config

## Kubernetes default configuration
DEFAULT_GLUSTERFS_ENDPOINT="glusterfs-cluster"


## Paddle distributed training default configuration
DEFAULT_PADDLE_PORT=7614
DEFAULT_PADDLE_PORT_NUM=2
DEFAULT_PADDLE_PORT_NUM_SPARSE=2

class PaddleJob(object):
    def __init__(self, trainers, pservers, base_image, glusterfs_volume,
                 input, output, job_name, namespace="default", **kwargs):
        self.trainers = trainers
        self.pservers = pservers
        self.base_iamge = base_image
        self.glusterfs_volume = glusterfs_volume
        self.input = input
        self.output = output
        self.job_name = job_name
        self.namespace = namespace
        self.user_env = kwargs.get("env", {})
        self.paddle_port = kwargs.get("paddle_port", DEFAULT_PADDLE_PORT)
        self.paddle_port_num = kwargs.get("paddle_port_num", DEFAULT_PADDLE_PORT_NUM)
        self.paddle_port_num_sparse = kwargs.get("paddle_port_num_sparse", DEFAULT_PADDLE_PORT_NUM_SPARSE)
        self.use_gpu = kwargs.get("use_gpu", False)

    def get_pserver_job_name(self):
        return "%s-pserver" % self.job_name

    def get_trainer_job_name(self):
        return "%s-trainer" % self.job_name

    def get_env(self):
        envs = []
        for k, v in self.user_env.items():
            env = client.V1EnvVar()
            env.name = k
            env.value = v
            envs.append(env)
        envs.append(client.V1EnvVar(name="PORT", value="7614"))
        envs.append(client.V1EnvVar(name="PADDLE_PORTS_NUM", value="2"))
        envs.append(client.V1EnvVar(name="PADDLE_PORTS_NUM_SPARSE", value="2"))
        envs.append(client.V1EnvVar(name="NICES", value="eth0"))
        envs.append(client.V1EnvVar(name="PADDLE_GRADIENT_NUM", value="3"))
        envs.append(client.V1EnvVar(name="PADDLE_JOB_NAME", value=self.job_name))
        envs.append(client.V1EnvVar(name="INPUT", value=self.input))
        envs.append(client.V1EnvVar(name="OUTPUT", value=self.output))
        envs.append(client.V1EnvVar(name="USE_GPU", value=str(self.use_gpu)))
        envs.append(client.V1EnvVar(name="TRAINER_COUNT", value=str(self.trainers)))
        envs.append(client.V1EnvVar(
            name="NAMESPACE", value_from=client.V1EnvVarSource(
                field_ref=client.V1ObjectFieldSelector(field_path="metadata.namespace"))))
        envs.append(client.V1EnvVar(name="TRAINER_PACKAGE", value="/root/trainer"))
        return envs

    def get_pserver_container_ports(self):
        ports = []
        port = self.paddle_port
        for i in xrange(self.paddle_port_num + self.paddle_port_num_sparse):
            ports.append(client.V1ContainerPort(container_port=port, name="jobport-%d"% i))
            port+=1
        return ports

    def get_pserver_labels(self):
        return {"paddle-job":self.get_pserver_job_name()}

    def get_pserver_entrypoint(self):
        return ["paddle_k8s", "start_pserver"]

    def get_trainer_entrypoint(sefl):
        return ["paddle_k8s", "start_trainer"]

    def get_trainer_labels(self):
        return {"paddle-job":self.get_trainer_job_name()}

    def get_runtime_docker_image_name(self):
        #TODO: use runtime docker image
        return self.base_iamge
        #return "%s-%s:latest" % (self.namespace, self.job_name)

    def new_pserver_job(self):
        return client.V1beta1StatefulSet(
            metadata = client.V1ObjectMeta(
                name = self.get_pserver_job_name()
            ),
            spec = client.V1beta1StatefulSetSpec(
                service_name    = self.get_pserver_job_name(),
                replicas        = self.pservers,
                template        = client.V1PodTemplateSpec (
                    metadata = client.V1ObjectMeta(
                        labels = self.get_pserver_labels()
                    ),
                    spec = client.V1PodSpec(
                        containers = [
                            client.V1Container(
                                name    =   self.get_pserver_job_name(),
                                image   =   self.get_runtime_docker_image_name(),
                                ports   =   self.get_pserver_container_ports(),
                                env     =   self.get_env(),
                                command =   self.get_pserver_entrypoint()
                            )
                        ]
                    )
                )
            )
        )

    def new_trainer_job(self):
        return client.V1Job(
            metadata = client.V1ObjectMeta (
                name = self.get_trainer_job_name()
            ),
            spec = client.V1JobSpec(
                parallelism = self.trainers,
                completions = self.trainers,
                template    = client.V1PodTemplateSpec (
                    metadata    = client.V1ObjectMeta (
                        labels  = self.get_trainer_labels()
                    ),
                    spec = client.V1PodSpec (
                        volumes=[
                            client.V1Volume(
                                name = "glusterfsvol",
                                glusterfs=client.V1GlusterfsVolumeSource(
                                    endpoints   = DEFAULT_GLUSTERFS_ENDPOINT,
                                    path        = self.glusterfs_volume
                                )
                            )
                        ],
                        containers=[
                            client.V1Container(
                                name                = "trainer",
                                image               = self.get_runtime_docker_image_name(),
                                image_pull_policy   = "Always",
                                command             = self.get_trainer_entrypoint(),
                                env                 = self.get_env(),
                                volume_mounts       = [
                                    client.V1VolumeMount(
                                        mount_path="/mnt/glusterfs",
                                        name="glusterfsvol"
                                    )
                                ]

                            )
                        ],
                        restart_policy = "Never"
                    )

                )
            )
        )
