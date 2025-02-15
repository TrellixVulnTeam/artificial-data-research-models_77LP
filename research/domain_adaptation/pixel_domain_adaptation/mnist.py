#  Copyright 2017 The TensorFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
"""Convolutional Neural Network Estimator for MNIST, built with tf.layers."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from absl import app as absl_app
from absl import flags
import tensorflow as tf  # pylint: disable=g-bad-import-order

from official.utils.flags import core as flags_core
from official.utils.logs import hooks_helper
from official.utils.misc import model_helpers

import os
import functools
import imageio

LEARNING_RATE = 1e-4

class dataset:
	def folder_generator(path):
		for filename in os.listdir(path):
			parts = filename.split(".")
			label = int(parts[-2])

			fullfile = path + "/" + filename

			image = imageio.imread(fullfile)
			image = image.astype(float)
			image = image.reshape((784))
			image = image / 255.

			yield (image, label)

	def train(datadir):
		return tf.data.Dataset.from_generator(functools.partial(dataset.folder_generator, datadir + "/train"), output_types=(tf.float32, tf.int32), output_shapes=((784,), ())).cache(datadir + "/train.cache")

	def test(datadir):
		return tf.data.Dataset.from_generator(functools.partial(dataset.folder_generator, datadir + "/test"), output_types=(tf.float32, tf.int32), output_shapes=((784,), ()))
		


def create_model(data_format):
  """Model to recognize digits in the MNIST dataset.

  Network structure is equivalent to:
  https://github.com/tensorflow/tensorflow/blob/r1.5/tensorflow/examples/tutorials/mnist/mnist_deep.py
  and
  https://github.com/tensorflow/models/blob/master/tutorials/image/mnist/convolutional.py

  But uses the tf.keras API.

  Args:
    data_format: Either 'channels_first' or 'channels_last'. 'channels_first' is
      typically faster on GPUs while 'channels_last' is typically faster on
      CPUs. See
      https://www.tensorflow.org/performance/performance_guide#data_formats

  Returns:
    A tf.keras.Model.
  """
  if data_format == 'channels_first':
    input_shape = [1, 28, 28]
  else:
    assert data_format == 'channels_last'
    input_shape = [28, 28, 1]

  l = tf.keras.layers
  max_pool = l.MaxPooling2D(
      (2, 2), (2, 2), padding='same', data_format=data_format)
  # The model consists of a sequential chain of layers, so tf.keras.Sequential
  # (a subclass of tf.keras.Model) makes for a compact description.
  return tf.keras.Sequential(
      [
          l.Reshape(
              target_shape=input_shape,
              input_shape=(28 * 28,)),
          l.Conv2D(
              32,
              5,
              padding='same',
              data_format=data_format,
              activation=tf.nn.relu),
          max_pool,
          l.Conv2D(
              64,
              5,
              padding='same',
              data_format=data_format,
              activation=tf.nn.relu),
          max_pool,
          l.Flatten(),
          l.Dense(1024, activation=tf.nn.relu),
          l.Dropout(0.4),
          l.Dense(10)
      ])


def define_mnist_flags():
  flags_core.define_base(multi_gpu=True, num_gpu=False)
  flags_core.define_image()
  flags.adopt_module_key_flags(flags_core)
  flags_core.set_defaults(data_dir='/opt/mnist_data',
                          model_dir='/tmp/mnist_model',
                          batch_size=100,
                          train_epochs=40)


def model_fn(features, labels, mode, params):
  """The model_fn argument for creating an Estimator."""
  model = create_model(params['data_format'])
  image = features
  if isinstance(image, dict):
    image = features['image']

  if mode == tf.estimator.ModeKeys.PREDICT:
    logits = model(image, training=False)
    predictions = {
        'classes': tf.argmax(logits, axis=1),
        'probabilities': tf.nn.softmax(logits),
    }
    return tf.estimator.EstimatorSpec(
        mode=tf.estimator.ModeKeys.PREDICT,
        predictions=predictions,
        export_outputs={
            'classify': tf.estimator.export.PredictOutput(predictions)
        })
  if mode == tf.estimator.ModeKeys.TRAIN:
    optimizer = tf.train.AdamOptimizer(learning_rate=LEARNING_RATE)

    # If we are running multi-GPU, we need to wrap the optimizer.
    if params.get('multi_gpu'):
      optimizer = tf.contrib.estimator.TowerOptimizer(optimizer)

    logits = model(image, training=True)
    loss = tf.losses.sparse_softmax_cross_entropy(labels=labels, logits=logits)
    accuracy = tf.metrics.accuracy(
        labels=labels, predictions=tf.argmax(logits, axis=1))

    # Name tensors to be logged with LoggingTensorHook.
    tf.identity(LEARNING_RATE, 'learning_rate')
    tf.identity(loss, 'cross_entropy')
    tf.identity(accuracy[1], name='train_accuracy')

    # Save accuracy scalar to Tensorboard output.
    tf.summary.scalar('train_accuracy', accuracy[1])

    return tf.estimator.EstimatorSpec(
        mode=tf.estimator.ModeKeys.TRAIN,
        loss=loss,
        train_op=optimizer.minimize(loss, tf.train.get_or_create_global_step()))
  if mode == tf.estimator.ModeKeys.EVAL:
    logits = model(image, training=False)
    loss = tf.losses.sparse_softmax_cross_entropy(labels=labels, logits=logits)
    return tf.estimator.EstimatorSpec(
        mode=tf.estimator.ModeKeys.EVAL,
        loss=loss,
        eval_metric_ops={
            'accuracy':
                tf.metrics.accuracy(
                    labels=labels, predictions=tf.argmax(logits, axis=1)),
        })


def validate_batch_size_for_multi_gpu(batch_size):
  """For multi-gpu, batch-size must be a multiple of the number of GPUs.

  Note that this should eventually be handled by replicate_model_fn
  directly. Multi-GPU support is currently experimental, however,
  so doing the work here until that feature is in place.

  Args:
    batch_size: the number of examples processed in each training batch.

  Raises:
    ValueError: if no GPUs are found, or selected batch_size is invalid.
  """
  from tensorflow.python.client import device_lib  # pylint: disable=g-import-not-at-top

  local_device_protos = device_lib.list_local_devices()
  num_gpus = sum([1 for d in local_device_protos if d.device_type == 'GPU'])
  if not num_gpus:
    raise ValueError('Multi-GPU mode was specified, but no GPUs '
                     'were found. To use CPU, run without --multi_gpu.')

  remainder = batch_size % num_gpus
  if remainder:
    err = ('When running with multiple GPUs, batch size '
           'must be a multiple of the number of available GPUs. '
           'Found {} GPUs with a batch size of {}; try --batch_size={} instead.'
          ).format(num_gpus, batch_size, batch_size - remainder)
    raise ValueError(err)


def run_mnist(flags_obj):
  """Run MNIST training and eval loop.

  Args:
    flags_obj: An object containing parsed flag values.
  """

  model_function = model_fn

  if flags_obj.multi_gpu:
    validate_batch_size_for_multi_gpu(flags_obj.batch_size)

    # There are two steps required if using multi-GPU: (1) wrap the model_fn,
    # and (2) wrap the optimizer. The first happens here, and (2) happens
    # in the model_fn itself when the optimizer is defined.
    model_function = tf.contrib.estimator.replicate_model_fn(
        model_fn, loss_reduction=tf.losses.Reduction.MEAN)

  data_format = flags_obj.data_format
  if data_format is None:
    data_format = ('channels_first'
                   if tf.test.is_built_with_cuda() else 'channels_last')
  mnist_classifier = tf.estimator.Estimator(
      model_fn=model_function,
      model_dir=flags_obj.model_dir,
      params={
          'data_format': data_format,
          'multi_gpu': flags_obj.multi_gpu
      })

  # Set up training and evaluation input functions.
  def train_input_fn():
    """Prepare data for training."""

    # When choosing shuffle buffer sizes, larger sizes result in better
    # randomness, while smaller sizes use less memory. MNIST is a small
    # enough dataset that we can easily shuffle the full epoch.
    ds = dataset.train(flags_obj.data_dir)
    ds = ds.cache().shuffle(buffer_size=50000).batch(flags_obj.batch_size)

    # Iterate through the dataset a set number (`epochs_between_evals`) of times
    # during each training session.
    ds = ds.repeat()
    ds = ds.take(1000000)
    return ds

  def eval_input_fn():
    return dataset.test(flags_obj.data_dir).batch(
        flags_obj.batch_size).make_one_shot_iterator().get_next()

  # Set up hook that outputs training logs every 100 steps.
  train_hooks = hooks_helper.get_train_hooks(
      flags_obj.hooks, batch_size=flags_obj.batch_size)

  # Train and evaluate model.
  for _ in range(flags_obj.train_epochs // flags_obj.epochs_between_evals):
    mnist_classifier.train(input_fn=train_input_fn, hooks=train_hooks)
    eval_results = mnist_classifier.evaluate(input_fn=eval_input_fn)
    print('\nEvaluation results:\n\t%s\n' % eval_results)

    if model_helpers.past_stop_threshold(flags_obj.stop_threshold,
                                         eval_results['accuracy']):
      break

  eval_results = mnist_classifier.evaluate(input_fn=eval_input_fn)
  print('\nEvaluation results:\n\t%s\n' % eval_results)

  # Export the model
  if flags_obj.export_dir is not None:
    image = tf.placeholder(tf.float32, [None, 28, 28])
    input_fn = tf.estimator.export.build_raw_serving_input_receiver_fn({
        'image': image,
    })
    mnist_classifier.export_savedmodel(flags_obj.export_dir, input_fn)


def main(_):
  run_mnist(flags.FLAGS)


if __name__ == '__main__':
  tf.logging.set_verbosity(tf.logging.INFO)
  define_mnist_flags()
  absl_app.run(main)
