import os
import sys
import tensorflow as tf
import numpy as np
import random
import time

from setup_imagenet import ImageNet, ImageNetModel

from l2_attack import CarliniL2
from l1_attack import EADL1

from utils_for_test import linf_loss, l0_loss, l1_loss, l2_loss, dump, generate_data

def main(args):

    with tf.Session() as sess:

        random.seed(args["seed"])
        np.random.seed(args["seed"])
        tf.set_random_seed(args["seed"])

        print("seed = ", args["seed"])

        overall_timestart = time.time()

        use_log = not args['use_zvalue']

        print("use_log = ", use_log)

        data_map = {
        }

        model_map = {
        }

        if args['dataset'] == "imagenet":
            if args['attack'] == "CW":
                model_map[args['model_name']] = ImageNetModel(sess, use_log, args['model_name'], create_prediction=False)
            elif args['attack'] == "EADL1":
                model_map[args['model_name']] = ImageNetModel(sess, use_log, args['model_name'], create_prediction=True)

            data_map['imagenet'] = ImageNet(model_map[args['model_name']].image_size, load_total_imgs=args['numimg_loaded'])


        print('Loading model', args['dataset'])
        data = data_map[args['dataset']]
        model = model_map[args['model_name']]

        if args['numimg'] == 0:
            args['numimg'] = len(data.test_labels) - args['firstimg']
        print('Using', args['numimg'], 'test images')
        # load attack module

        print('args = ', args)

        targeted_flag = not args['untargeted']

        print("targeted_flag = ", targeted_flag)
		

        # load attack module
        if args['attack'] == "CW":

            attack = CarliniL2(sess, model, 100)
            attack_predictor = attack.predict
        elif args['attack'] == "EADL1":
            attack_predictor = model.model.predict

        random.seed(args['seed'])
        np.random.seed(args['seed'])
        tf.set_random_seed(args['seed'])

        print('Generate data')
        model_name = args['model_name']

        if 'vgg' in model_name or 'densenet' in model_name or 'alexnet' in model_name:
            remove_background_class_flag = True
        else:
            remove_background_class_flag = False

        sys.stdout.flush()

        all_inputs, all_targets, all_labels, all_true_ids, img_info = generate_data(data, samples=args['numimg'],
        targeted=targeted_flag, random_and_least_likely = True, predictor=attack_predictor,
        start=args['firstimg'], imagenet=isinstance(data, ImageNet),
        remove_background_class=remove_background_class_flag, target_type=args['target_type'],
        total_num_valid_samples=args['num_valid_test_imgs'])

        print('len(all_inputs) = ', len(all_inputs))
        print("all_inputs shape:",all_inputs.shape)
        print("all_targets shape:", all_targets.shape)

        attack_batch_size = args['attack_batch_size']
        if attack_batch_size == 0:
            attack_batch_size = all_true_ids.size
        print("attack_batch_size = ", attack_batch_size)

        if args['attack'] == 'CW':
            attack.init_attack(sess, model, targeted=targeted_flag, batch_size=attack_batch_size,
                           initial_const=args['init_const'], binary_search_steps=args['binary_steps'],
                           max_iterations=args['maxiter'], print_every=args['print_every'],
                            confidence=args['kappa'], use_log=use_log)

        elif args['attack'] == 'EADL1':
            print("EADL1 attack")
            attack = EADL1(sess, model, targeted=targeted_flag, batch_size=attack_batch_size,
                           initial_const=args['init_const'], binary_search_steps=args['binary_steps'],
                           max_iterations=args['maxiter'], confidence=args['kappa'],
                           print_every=args['print_every'])

        else:
            print("Invalid attack name, exit 1")
            return

        saved_path = "{}/{}/{}/targeted_{}".format(args['save'], args['dataset'], args['attack'], targeted_flag)
        if not os.path.exists(saved_path):    
            os.system("mkdir -p " + saved_path)

        img_no = 0
        total_success = 0
        l0_list = []
        l1_list = []
        l2_list = []
        linf_list = []
        time_list = []

        verbose_f = open(args['save'] + "/" + "_".join([args['dataset'], args['attack'], str(targeted_flag), "verbose.txt"]), "w")
        aggre_f = open(args['save'] + "/" + "_".join([args['dataset'], args['attack'], str(targeted_flag), "aggre.txt"]), "w")

        if targeted_flag == True:
            verbose_head_str = '\t'.join(['total', 'seq', 'id', 'time', 'success', 'prev_class', 'target',
                                          'new_class', 'l0_distortion', 'l1_distortion', 'l2_distortion',
                                          'linf_distortion'])
        else:
            verbose_head_str = '\t'.join(['total', 'seq', 'id', 'time', 'success', 'prev_class', 'new_class',
                                          'l0_distortion', 'l1_distortion', 'l2_distortion', 'linf_distortion'])

        aggre_head_str = '\t'.join(['total_count', 'success_rate', 'l0_avg', 'l0_std', 'l1_avg', 'l1_std',
                                    'l2_avg', 'l2_std', 'linf_avg', 'linf_std', 'time_avg', 'time_std'])

        verbose_f.write(verbose_head_str + '\n')
        aggre_f.write(aggre_head_str + '\n')

        print("all_true_ids.size = ", all_true_ids.size)
        sys.stdout.flush()

        random.seed(args['seed'])
        np.random.seed(args['seed'])
        tf.set_random_seed(args['seed'])

        for i in range(0, all_true_ids.size, attack_batch_size):

            if i + attack_batch_size > all_true_ids.size:
                actual_attack_batch_size = all_true_ids.size - i
            else:
                actual_attack_batch_size = attack_batch_size

            inputs = all_inputs[i:i+actual_attack_batch_size]
            targets = all_targets[i:i+actual_attack_batch_size]
            labels = all_labels[i:i+actual_attack_batch_size]

            timestart = time.time()

            """perform the attack"""
            print("perform the attack")
            adv = attack.attack(inputs, targets)

            timeend = time.time()

            time_used = timeend - timestart
            time_used_per_image = time_used / attack_batch_size

            for j in range(len(adv)):

                print("="*10, "i = ", i, "="*10, "j=", j, "="*10)

                # original_predict = np.squeeze(attack.predict(np.array([inputs[j]])))
                original_predict = np.squeeze(attack_predictor(np.array([inputs[j]])))

                original_prob = np.sort(original_predict)
                original_class = np.argsort(original_predict)
                print("Original Classification:", original_prob[-1:-6:-1])
                print("Original Probabilities/Logits:", original_class[-1:-6:-1])
                sys.stdout.flush()

                true_label = np.argmax(labels[j])
                target_label = np.argmax(targets[j])
                attack_label = None
                success = False

                img_no += 1

                print("Target:", target_label)
                # if the array contains NaN, the solver did not return a solution
                if (np.any(np.isnan(adv[j]))):
                    print('Attack failed. (solver returned NaN)')
                    l0_distortion = l1_distortion = l2_distortion = linf_distortion = np.nan
                    adversarial_class = np.zeros(original_class.shape)

                else:
                    l0_distortion = l0_loss(adv[j], inputs[j])
                    l1_distortion = l1_loss(adv[j], inputs[j])
                    l2_distortion = l2_loss(adv[j], inputs[j])
                    linf_distortion = linf_loss(adv[j], inputs[j])
                    #adversarial_predict = np.squeeze(model.model.predict(np.array([adv[j]])))
                    # adversarial_predict = np.squeeze(attack.predict(np.array([adv[j]])))
                    adversarial_predict = np.squeeze(attack_predictor(np.array([adv[j]])))

                    adversarial_prob = np.sort(adversarial_predict)
                    adversarial_class = np.argsort(adversarial_predict)
                    attack_label = np.argmax(adversarial_predict)

                    print("adversarial probabilities:", adversarial_prob[-1:-11:-1])
                    print("adversarial classification:", adversarial_class[-1:-11:-1])
                    sys.stdout.flush()

                    success = False
                    if targeted_flag:
                        success = np.argsort(adversarial_predict)[-1] == target_label

                        candidates = set([i for i in range(len(adversarial_predict)-1)
                                          if abs(adversarial_predict[i] - adversarial_prob[-1]) < 0.001])
                        if len(candidates) > 1 and target_label in candidates:
                            success = True
                    else:
                        success = np.argsort(adversarial_predict)[-1] != target_label

                    if success:
                        print("Attack succeeded.")
                    else:
                        print("Attack failed.")

                    if success:
                        total_success += 1
                        l0_list.append(l0_distortion)
                        l1_list.append(l1_distortion)
                        l2_list.append(l2_distortion)
                        linf_list.append(linf_distortion)
                        time_list.append(time_used_per_image)

                suffix = "id={0}_seq={1}_prev={2}_adv={3}_res={4}".format(all_true_ids[i+j], i, original_class[-1],
                                                                          adversarial_class[-1], success)
                print("Saving to", suffix)
                sys.stdout.flush()

                dump(inputs[j], "{}/imgno={}_content={}_{}".format(saved_path, img_no, 'original', suffix))
                dump(adv[j], "{}/imgno={}_content={}_{}".format(saved_path, img_no, 'adversarial', suffix))
                # dump(adv[j] - inputs[j], "{}/imgno={}_content={}_{}".format(saved_path, img_no, 'noise', suffix))
                np.save("{}/imgno={}_content={}_{}".format(saved_path, img_no, 'targets', suffix) + ".npy", targets[j])
                np.save("{}/imgno={}_content={}_{}".format(saved_path, img_no, 'labels', suffix) + ".npy", labels[j])

                L1_debug_str = "[STATS][L1] total = {}, seq = {}, id = {}, time = {:.3f}, success = {}, " \
                               "prev_class = {}, new_class = {}, distortion = {:.5f}, success_rate = {:.3f}, " \
                               "l2_avg = {:.5f}".format(img_no, i+j, all_true_ids[i+j], time_used_per_image, success,
                                original_class[-1], adversarial_class[-1], l2_distortion,
                                total_success / float(img_no), 0 if total_success == 0 else np.mean(l2_list))

                print(L1_debug_str)
                sys.stdout.flush()

                if targeted_flag == True:
                    verbose_str = '\t'.join(
                        [str(img_no), str(i+j), str(all_true_ids[i+j]), str(time_used_per_image), str(success),
                         str(original_class[-1]), str(np.argmax(targets[j])), str(adversarial_class[-1]),
                         str(l0_distortion), str(l1_distortion), str(l2_distortion), str(linf_distortion)])
                else:
                    verbose_str = '\t'.join(
                        [str(img_no), str(i+j), str(all_true_ids[i+j]), str(time_used_per_image), str(success),
                         str(original_class[-1]), str(adversarial_class[-1]), str(l0_distortion), str(l1_distortion),
                         str(l2_distortion), str(linf_distortion)])

                verbose_f.write(verbose_str + "\n")
                verbose_f.flush()
                print(verbose_head_str)
                print(verbose_str)

                sys.stdout.flush()

                overall_timeend_sofar = time.time()

                overall_time_used_sofar = overall_timeend_sofar - overall_timestart

                print("overall_time_used_sofar = ", overall_time_used_sofar)
                sys.stdout.flush()

        verbose_f.close()

        if img_no == 0:
            success_rate = 0.0
        else:
            success_rate = total_success / float(img_no)

        if total_success == 0:
            aggre_str = "\t".join([str(img_no), str(success_rate), str(0.0), str(0.0), str(0.0), str(0.0),
                                   str(0.0), str(0.0), str(0.0), str(0.0), str(0.0), str(0.0)])
        else:
            aggre_str = "\t".join([str(img_no), str(success_rate), str(np.mean(l0_list)), str(np.std(l0_list)),
                                   str(np.mean(l1_list)), str(np.std(l1_list)), str(np.mean(l2_list)),
                                   str(np.std(l2_list)), str(np.mean(linf_list)), str(np.std(linf_list)),
                                   str(np.mean(time_list)), str(np.std(time_list))])

        aggre_f.write(aggre_str + "\n")
        print(aggre_head_str)
        print(aggre_str)
        sys.stdout.flush()
        aggre_f.close()

        overall_timeend = time.time()

        overall_time_used = overall_timeend - overall_timestart

        print("overall_time_used = ", overall_time_used)
        sys.stdout.flush()

        print("ALL DONE!!!")
        return

if __name__ == "__main__":

    import argparse
    parser = argparse.ArgumentParser()

    parser.add_argument("-d", "--dataset", choices=["imagenet"], default="imagenet")
    parser.add_argument("-s", "--save", default="./saved_results")

    parser.add_argument("-a", "--attack", choices=["CW", "EADL1"], default="CW")
    parser.add_argument("-u", "--untargeted", action='store_true')

    parser.add_argument("--num_valid_test_imgs", type=int, default=1000)

    parser.add_argument("--attack_batch_size", type=int, default=0)

    parser.add_argument( "--target_type", type=int, default=0b0111)

    parser.add_argument("--model_name", default="resnet_v2_50")

    parser.add_argument("-n", "--numimg", type=int, default=0, help = "number of test images to attack")
    parser.add_argument("-m", "--maxiter", type=int, default=0, help = "set 0 to use default value")

    parser.add_argument("-p", "--print_every", type=int, default=10, help = "print objs every PRINT_EVERY iterations")
    parser.add_argument("-o", "--early_stop_iters", type=int, default=100, help = "print objs every EARLY_STOP_ITER iterations, 0 is maxiter//10")
    parser.add_argument("-f", "--firstimg", type=int, default=0)
    parser.add_argument("--numimg_loaded", type=int, default=1000, help = "number of test images to load")        

    parser.add_argument('-l', '--loss_function', choices=['l0', 'l1', 'l2', 'linf'], default='linf')

    parser.add_argument("-b", "--binary_steps", type=int, default=0)
    parser.add_argument("-c", "--init_const", type=float, default=0.0)
    parser.add_argument("-z", "--use_zvalue", action='store_true')

    parser.add_argument("-r", "--reset_adam", action='store_true', help = "reset adam after an initial solution is found")
    parser.add_argument("--use_resize", action='store_true', help = "resize image (only works on imagenet!)")
    parser.add_argument("--adam_beta1", type=float, default=0.9)
    parser.add_argument("--adam_beta2", type=float, default=0.999)
    parser.add_argument("--seed", type=int, default=1216)
    parser.add_argument("--solver", choices=["adam", "newton", "adam_newton", "fake_zero"], default="adam")
    parser.add_argument("--save_ckpts", default="", help = "path to save checkpoint file")
    parser.add_argument("--load_ckpt", default="", help = "path to numpy checkpoint file")
    parser.add_argument("--start_iter", default=0, type=int, help = "iteration number for start, useful when loading a checkpoint")
    parser.add_argument("--init_size", default=32, type=int, help = "starting with this size when --use_resize")
    parser.add_argument("--uniform", action='store_true', help = "disable importance sampling")
    parser.add_argument("--lr", type=float, default=1e-2, help = "learning rate")
    parser.add_argument("--kappa", type=int, default=0, help = "initial_constance")
    args = vars(parser.parse_args())

    # setup random seed
    random.seed(args['seed'])
    np.random.seed(args['seed'])
    tf.set_random_seed(args['seed'])
    print(args)

    main(args)

    print("Experiment Done!!!")

