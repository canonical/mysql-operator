
# Build your first ML model

This tutorial walks you through some of the main components of Charmed Kubeflow (CKF). By the end of it, you will have created a complete end-to-end Machine Learning (ML) pipeline using [Kubeflow Pipelines](https://www.kubeflow.org/docs/components/pipelines/overview/), [MLflow](https://mlflow.org/) and [KServe](https://kserve.github.io/website/latest/).

First, you will use Kubeflow Notebooks to create and connect to a [JupyterLab](https://jupyter.org/) environment. Then, you will create a Kubeflow Pipeline to process a wine dataset, train it on an ML model and predict its quality. Finally, you will store the model in the MLflow registry, and leverage the KServe inference service for model deployment.

```{note}

You can download the code used for this tutorial as a Jupyter Notebook [here](https://github.com/canonical/kubeflow-examples/blob/88d0ba44725359db687a25e51ab1c68ff479d506/explore-components/explore-components.ipynb).

```

## Requirements

* Charmed Kubeflow (CKF) has been deployed on your machine. See [Get started](https://charmed-kubeflow.io/docs/get-started-with-charmed-kubeflow) for more details.
* MLflow has been deployed and connected with Kubeflow. See [this tutorial](https://documentation.ubuntu.com/charmed-mlflow/en/latest/tutorial/mlflow-kubeflow/) for more details.

## Kubeflow notebooks

From the sidebar of the Kubeflow central dashboard, go to `Notebooks` and click on `New Notebook`. Enter a name for your notebook, and select the `kubeflownotebookswg/jupyter-scipy:v1.9.0` image:

![new_notebook](https://assets.ubuntu.com/v1/fdef0086-kubeflow-central-dashboard.png)

From `Advanced Options`, go to `Configurations` and allow access to Kubeflow Pipelines, [MinIO](https://min.io/), and MLflow from the dropdown menu:
https://assets.ubuntu.com/v1/44319046-allow-access.png

This ensures the correct credentials are injected into the JupyterLab environment, simplifying the interaction with MLflow and MinIO.

After you have configured your notebook server, click on `Launch` to create it. Wait until the server status is `Running`, indicated by a green check mark, and then click on `Connect` to view the server web interface.

From the JupyterLab interface, create a new Python 3 Jupyter Notebook:

![jupyter_notebook](https://assets.ubuntu.com/v1/2d3fe39c-create-jupyter-notebook.png)

Now install the Python packages required for the remaining of the tutorial:

```python
!pip install mlflow==2.15.1 kserve==0.13.1 tenacity
```

## Kubeflow pipelines

A Kubeflow pipeline is a definition of a workflow that composes one or more components together to form a computational Directed Acyclic Graph (DAG). Each component execution corresponds to a Docker container execution. See [Kubeflow Pipelines overview](https://www.kubeflow.org/docs/components/pipelines/overview/) for more details.

In this tutorial, you will create a Kubeflow pipeline that consists of the following steps:

1. Data ingestion: downloading a wine quality dataset from a public URL.
2. Data preprocessing: cleaning and transforming the dataset into a format suitable for model training.
3. Model training: training an ElasticNet regression model to predict wine quality, with automatic logging of model artefacts to MLflow.
4. Model deployment: deploying the trained model as a scalable inference service using KServe.

First, import the necessary components required for the remaining of the tutorial:

```python
import kfp
import mlflow
import os
import requests

from kfp.dsl import Input, Model, component
from kfp.dsl import InputPath, OutputPath, pipeline, component
from kserve import KServeClient
from mlflow.tracking import MlflowClient
from tenacity import retry, stop_after_attempt, wait_exponential
```

### Ingest your data

Create a component that downloads the sample dataset, imports it as a `.csv` file and then saves it at a specified path:
```python
@component(
    base_image="python:3.11",
    packages_to_install=["requests==2.32.3", "pandas==2.2.2"]
)
def download_dataset(url: str, dataset_path: OutputPath('Dataset')) -> None:
    import requests
    import pandas as pd

    response = requests.get(url)
    response.raise_for_status()

    from io import StringIO
    dataset = pd.read_csv(StringIO(response.text), header=0, sep=";")

    dataset.to_csv(dataset_path, index=False)
```
### Process the data

Create a component that preprocesses the dataset and saves it as an [Apache Parquet](https://parquet.apache.org/) file for a more efficient storage:
```python
@component(
    base_image="python:3.11",
    packages_to_install=["pandas==2.2.2", "pyarrow==15.0.2"]
)
def preprocess_dataset(dataset: InputPath('Dataset'), output_file: OutputPath('Dataset')) -> None:
    import pandas as pd
    
    df = pd.read_csv(dataset, header=0)
    df.columns = [c.lower().replace(" ", "_") for c in df.columns]
    df.to_parquet(output_file)

```
### Train an ML model

Now that the dataset is preprocessed, you can write a component that splits the dataset into training and testing data, trains an ElasticNet regression model, and logs all model artefacts to MLflow:

```python
@component(
    base_image="python:3.11",
    packages_to_install=["pandas==2.2.2", "scikit-learn==1.5.1", "mlflow==2.15.1", "pyarrow==15.0.2", "boto3==1.34.162"]
)
def train_model(dataset: InputPath('Dataset'), run_name: str, model_name: str) -> str:
    import os
    import mlflow
    import pandas as pd
    from sklearn.linear_model import ElasticNet
    from sklearn.model_selection import train_test_split

    df = pd.read_parquet(dataset)
    
    target_column = "quality"

    train_x, test_x, train_y, test_y = train_test_split(
        df.drop(columns=[target_column]),
        df[target_column], test_size=0.25,
        random_state=42, stratify=df[target_column]
    )

    mlflow.sklearn.autolog()
    
    with mlflow.start_run(run_name=run_name) as run:
        mlflow.set_tag("author", "kf-testing")
        lr = ElasticNet(alpha=0.5, l1_ratio=0.5, random_state=42)
        lr.fit(train_x, train_y)
        mlflow.sklearn.log_model(lr, "model", registered_model_name=model_name)
        
        model_uri = f"{run.info.artifact_uri}/model"
        print(model_uri)
        return model_uri
```

### Deploy the ML model

After the model has been trained, you can create a KServe inference service to enable scalable and performant model inference using HTTP requests. See [KServe documentation](https://kserve.github.io/website/0.13/get_started/first_isvc/) for more details. 

Write a component that creates a KServe inference service and returns its URL as follows:

```python
@component(
    base_image="python:3.11",
    packages_to_install=["kserve==0.13.1", "kubernetes==26.1.0", "tenacity==9.0.0"]
)
def deploy_model_with_kserve(model_uri: str, isvc_name: str) -> str:
    from kubernetes.client import V1ObjectMeta
    from kserve import (
        constants,
        KServeClient,
        V1beta1InferenceService,
        V1beta1InferenceServiceSpec,
        V1beta1PredictorSpec,
        V1beta1SKLearnSpec,
    )
    from tenacity import retry, wait_exponential, stop_after_attempt

    isvc = V1beta1InferenceService(
        api_version=constants.KSERVE_V1BETA1,
        kind=constants.KSERVE_KIND,
        metadata=V1ObjectMeta(
            name=isvc_name,
            annotations={"sidecar.istio.io/inject": "false"},
        ),
        spec=V1beta1InferenceServiceSpec(
            predictor=V1beta1PredictorSpec(
                service_account_name="kserve-controller-s3",
                sklearn=V1beta1SKLearnSpec(
                    storage_uri=model_uri
                )
            )
        )
    )
    
    client = KServeClient()
    client.create(isvc)

    @retry(
        wait=wait_exponential(multiplier=2, min=1, max=10),
        stop=stop_after_attempt(30),
        reraise=True,
    )
    def assert_isvc_created(client, isvc_name):
        assert client.is_isvc_ready(isvc_name), f"Failed to create Inference Service {isvc_name}."

    assert_isvc_created(client, isvc_name)
    isvc_resp = client.get(isvc_name)
    isvc_url = isvc_resp['status']['address']['url']
    print("Inference URL:", isvc_url)
    
    return isvc_url
```

### Create a pipeline

Create a pipeline that combines all the components you defined in the previous sections:
```python
ISVC_NAME = "wine-regressor4"
MLFLOW_RUN_NAME = "elastic_net_models"
MLFLOW_MODEL_NAME = "wine-elasticnet"

mlflow_tracking_uri = os.getenv('MLFLOW_TRACKING_URI')
mlflow_s3_endpoint_url = os.getenv('MLFLOW_S3_ENDPOINT_URL')
aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')

@pipeline(name='download-preprocess-train-deploy-pipeline')
def download_preprocess_train_deploy_pipeline(url: str):
    download_task = download_dataset(url=url)
    
    preprocess_task = preprocess_dataset(
        dataset=download_task.outputs['dataset_path']
    )
    
    train_task = train_model(
        dataset=preprocess_task.outputs['output_file'], run_name=MLFLOW_RUN_NAME, model_name=MLFLOW_MODEL_NAME
    ).set_env_variable(name='MLFLOW_TRACKING_URI', value=mlflow_tracking_uri)\
     .set_env_variable(name='MLFLOW_S3_ENDPOINT_URL', value=mlflow_s3_endpoint_url)\
     .set_env_variable(name='AWS_ACCESS_KEY_ID', value=aws_access_key_id)\
     .set_env_variable(name='AWS_SECRET_ACCESS_KEY', value=aws_secret_access_key)
    
    deploy_task = deploy_model_with_kserve(
        model_uri=train_task.output, isvc_name=ISVC_NAME
    ).set_env_variable(name='AWS_SECRET_ACCESS_KEY', value=aws_secret_access_key)
```

### Execute the pipeline

To execute the pipeline, you first have to initialise a Kubeflow Pipelines (KFP) client to interact with the Kubeflow Pipelines API. Then, you must compile the pipeline to a compatible YAML file and create a run from the produced YAML file as follows:

```python
client = kfp.Client()

url = 'https://raw.githubusercontent.com/canonical/kubeflow-examples/main/e2e-wine-kfp-mlflow/winequality-red.csv'

kfp.compiler.Compiler().compile(download_preprocess_train_deploy_pipeline, 'download_preprocess_train_deploy_pipeline.yaml')

run = client.create_run_from_pipeline_func(download_preprocess_train_deploy_pipeline, arguments={'url': url}, enable_caching=False)
```

You can check the run information by clicking on `Run Details` from the cell’s output. 

You can also check the graph view of the compiled pipeline and related components:

![pipeline](https://assets.ubuntu.com/v1/e139fee5-run-details.png)

Next, write and execute a function that continuously checks whether the run has finished and was successful:
```python
@retry(
    wait=wait_exponential(multiplier=2, min=1, max=10),
    stop=stop_after_attempt(90),
    reraise=True,
)
def assert_kfp_run_succeeded(client, run_id):
    run = client.get_run(run_id=run_id)
    state = run.state
    assert state == "SUCCEEDED", f"KFP run is in {state} state."

assert_kfp_run_succeeded(client, run.run_id)
```
```{note}
The run may take up to 10 minutes to complete.
```

## MLflow

The pipeline compiled in the previous section registers an MLflow experiment, used for tracking parameters, metrics, artifacts, data and environment configuration. Additionally, the ElasticNet regression model is also stored in the MLflow [model registry](https://mlflow.org/docs/latest/model-registry.html), which enables model versioning, aliasing, tracking and annotations.

To view the MLflow tracking User Interface (UI), select `MLflow` from the Kubeflow central dashboard sidebar. Within `Experiments`, you can see information about each experiment, including used dataset, hyperparameters and model metrics: 

![mlflow_exp](https://assets.ubuntu.com/v1/30dc857b-mlflow-experiments.png)

Within `Models`, you can see information related to registered models, including description, tags and version: 

![mlflow_mod](https://assets.ubuntu.com/v1/746f02ba-mlflow-models.png)

## KServe

A KServe client can be used to interact with the KServe inference service. You can use the client to send data to the deployed model via a POST request, and receive the model output as follows:

```python
kserve_client = KServeClient()

isvc_resp = kserve_client.get(ISVC_NAME)
inference_service_url = isvc_resp['status']['address']['url']
print("Inference URL:", inference_service_url)

input_data = {
    "instances": [
        [7.4, 0.7, 0.0, 1.9, 0.076, 11.0, 34.0, 0.9978, 3.51, 0.56, 9.4],
        [7.8, 0.88, 0.0, 2.6, 0.098, 25.0, 67.0, 0.9968, 3.2, 0.68, 9.8]
    ]
}

response = requests.post(f"{inference_service_url}/v1/models/{ISVC_NAME}:predict", json=input_data)
print(response.text)
```
## Clean up

To free up resources, use the KServe client to delete the inference service, and the MLflow client to delete the MLflow model:

```python
kserve_client.delete(ISVC_NAME)

@retry(
    wait=wait_exponential(multiplier=2, min=1, max=10),
    stop=stop_after_attempt(30),
    reraise=True,
)
def assert_isvc_deleted(kserve_client, isvc_name):
    try:
        isvc = kserve_client.get(isvc_name)
        assert not isvc, f"Failed to delete Inference Service {isvc_name}!"
    except RuntimeError as err:
        assert "Not Found" in str(err), f"Caught unexpected exception: {err}"

assert_isvc_deleted(kserve_client, ISVC_NAME)

client = MlflowClient()
client.delete_registered_model(name=MLFLOW_MODEL_NAME)
```

## Next steps

* To learn about common tasks and use cases for CKF, see [how-to guides](https://charmed-kubeflow.io/docs/how-to).
* To learn about the advantages of using CKF over upstream Kubeflow, see [Upstream vs Charmed Kubeflow](https://charmed-kubeflow.io/docs/charmed-vs--upstream-kubeflow).

-------------------------

