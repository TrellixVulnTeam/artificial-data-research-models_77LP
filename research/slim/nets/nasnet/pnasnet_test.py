# Copyright 2018 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Tests for slim.pnasnet."""




import tensorflow as tf

from nets.nasnet import pnasnet

slim = tf.contrib.slim


class PNASNetTest(tf.test.TestCase):

  def testBuildLogitsLargeModel(self):
    batch_size = 5
    height, width = 331, 331
    num_classes = 1000
    inputs = tf.random_uniform((batch_size, height, width, 3))
    tf.train.create_global_step()
    with slim.arg_scope(pnasnet.pnasnet_large_arg_scope()):
      logits, end_points = pnasnet.build_pnasnet_large(inputs, num_classes)
    auxlogits = end_points['AuxLogits']
    predictions = end_points['Predictions']
    self.assertListEqual(auxlogits.get_shape().as_list(),
                         [batch_size, num_classes])
    self.assertListEqual(logits.get_shape().as_list(),
                         [batch_size, num_classes])
    self.assertListEqual(predictions.get_shape().as_list(),
                         [batch_size, num_classes])

  def testBuildPreLogitsLargeModel(self):
    batch_size = 5
    height, width = 331, 331
    num_classes = None
    inputs = tf.random_uniform((batch_size, height, width, 3))
    tf.train.create_global_step()
    with slim.arg_scope(pnasnet.pnasnet_large_arg_scope()):
      net, end_points = pnasnet.build_pnasnet_large(inputs, num_classes)
    self.assertFalse('AuxLogits' in end_points)
    self.assertFalse('Predictions' in end_points)
    self.assertTrue(net.op.name.startswith('final_layer/Mean'))
    self.assertListEqual(net.get_shape().as_list(), [batch_size, 4320])

  def testAllEndPointsShapesLargeModel(self):
    batch_size = 5
    height, width = 331, 331
    num_classes = 1000
    inputs = tf.random_uniform((batch_size, height, width, 3))
    tf.train.create_global_step()
    with slim.arg_scope(pnasnet.pnasnet_large_arg_scope()):
      _, end_points = pnasnet.build_pnasnet_large(inputs, num_classes)

    endpoints_shapes = {'Stem': [batch_size, 42, 42, 540],
                        'Cell_0': [batch_size, 42, 42, 1080],
                        'Cell_1': [batch_size, 42, 42, 1080],
                        'Cell_2': [batch_size, 42, 42, 1080],
                        'Cell_3': [batch_size, 42, 42, 1080],
                        'Cell_4': [batch_size, 21, 21, 2160],
                        'Cell_5': [batch_size, 21, 21, 2160],
                        'Cell_6': [batch_size, 21, 21, 2160],
                        'Cell_7': [batch_size, 21, 21, 2160],
                        'Cell_8': [batch_size, 11, 11, 4320],
                        'Cell_9': [batch_size, 11, 11, 4320],
                        'Cell_10': [batch_size, 11, 11, 4320],
                        'Cell_11': [batch_size, 11, 11, 4320],
                        'global_pool': [batch_size, 4320],
                        # Logits and predictions
                        'AuxLogits': [batch_size, 1000],
                        'Predictions': [batch_size, 1000],
                        'Logits': [batch_size, 1000],
                       }
    self.assertEqual(len(end_points), 17)
    self.assertItemsEqual(list(endpoints_shapes.keys()), list(end_points.keys()))
    for endpoint_name in endpoints_shapes:
      tf.logging.info('Endpoint name: {}'.format(endpoint_name))
      expected_shape = endpoints_shapes[endpoint_name]
      self.assertIn(endpoint_name, end_points)
      self.assertListEqual(end_points[endpoint_name].get_shape().as_list(),
                           expected_shape)

  def testNoAuxHeadLargeModel(self):
    batch_size = 5
    height, width = 331, 331
    num_classes = 1000
    for use_aux_head in (True, False):
      tf.reset_default_graph()
      inputs = tf.random_uniform((batch_size, height, width, 3))
      tf.train.create_global_step()
      config = pnasnet.large_imagenet_config()
      config.set_hparam('use_aux_head', int(use_aux_head))
      with slim.arg_scope(pnasnet.pnasnet_large_arg_scope()):
        _, end_points = pnasnet.build_pnasnet_large(inputs, num_classes,
                                                    config=config)
      self.assertEqual('AuxLogits' in end_points, use_aux_head)

  def testOverrideHParamsLargeModel(self):
    batch_size = 5
    height, width = 331, 331
    num_classes = 1000
    inputs = tf.random_uniform((batch_size, height, width, 3))
    tf.train.create_global_step()
    config = pnasnet.large_imagenet_config()
    config.set_hparam('data_format', 'NCHW')
    with slim.arg_scope(pnasnet.pnasnet_large_arg_scope()):
      _, end_points = pnasnet.build_pnasnet_large(
          inputs, num_classes, config=config)
    self.assertListEqual(
        end_points['Stem'].shape.as_list(), [batch_size, 540, 42, 42])


if __name__ == '__main__':
  tf.test.main()
