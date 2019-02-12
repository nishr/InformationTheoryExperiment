import random
import torch as th
import numpy as np
import torch.nn as nn
from torch.autograd import Variable


class Network():
    def train_model(self, x, y, model, batch_size, gpu,
                    optimizer=th.optim.Adam):

        optimizer = optimizer(model.parameters())
        criterion = nn.CrossEntropyLoss()

        model.train()
        cost = []
        batches = self.make_batches(x.shape[0], batch_size)

        for batch in batches:
            optimizer.zero_grad()
            if gpu:
                batch_x = Variable(th.from_numpy(x[batch]).float()).cuda()
                batch_y = Variable(th.from_numpy(y[batch]).long()).cuda()
            else:
                batch_x = Variable(th.from_numpy(x[batch]).float())
                batch_y = Variable(th.from_numpy(y[batch]).long())

            output = model(batch_x)
            loss = criterion(output[0], batch_y)
            loss.backward()
            optimizer.step()
            cost.append(np.float32(loss.cpu().data))
        return np.mean(cost)

    def predict(self, x, y, model, batch_size, gpu):

        model.eval()
        scores = []
        batches = self.make_batches(x.shape[0], batch_size)

        for batch in batches:
            if gpu:
                batch_x = th.from_numpy(x[batch]).float().cuda()
                batch_y = th.from_numpy(y[batch]).long().cuda()
            else:
                batch_x = th.from_numpy(x[batch]).float()
                batch_y = th.from_numpy(y[batch]).long()

            output = model(batch_x)
            y_hat = th.argmax(self.softmax(output[0]), 1)
            scores.append(th.eq(batch_y, y_hat).sum().cpu().data.numpy() / batch_x.shape[0])

        return scores

    def dist_mat(self, x, y=None):

        try:
            x = th.from_numpy(x)
        except TypeError:
            x = x

        dist = th.norm(x[:, None] - x, dim=2, p=2)
        return dist

    def calc_kernel(self, x, n_n, sigma=None):

        k = self.dist_mat(x)

        if sigma is None:
            sigma = th.sort(k)[0][:, n_n].mean()
        else:
            sigma = sigma
        k = th.exp(-k ** 2 / sigma ** 2)

        return k / th.trace(k)

    def kernel_mat(self, x, n_n, sigma=None):

        try:
            x = th.from_numpy(x)
        except TypeError:
            x = x
        if len(x.shape) == 2:
            return self.calc_kernel(x, n_n, sigma=sigma)
        else:
            x = x.view(x.size(0), -1)
            return self.calc_kernel(x, n_n, sigma=sigma)

    def entropy(self, x, n_n, alpha, sigma=None):

        eigv = th.abs(th.symeig(x)[0])
        eig_pow = eigv**alpha
        return (1/(1-alpha))*th.log2(eig_pow.sum())

    def j_entropy(self, x, y, n_n, alpha, sigma=None):

        k = x*y / (th.trace(x*y))
        eigv = th.abs(th.symeig(k)[0])
        eig_pow = eigv**alpha
        return (1/(1-alpha))*th.log2(eig_pow.sum())

    def compute_mi(self, x, y, n_n, alpha, batch_size, model, gpu, sigma=None):

        model.eval()
        batches = list(self.make_batches(x.shape[0], batch_size))
        MI = []

        for idx, batch in enumerate(batches):
            MI_temp = []
            if gpu:
                batch_x = th.from_numpy(x[batch]).float().cuda()
                batch_y = th.from_numpy(y[batch]).long().cuda()
            else:
                batch_x = th.from_numpy(x[batch]).float()
                batch_y = th.from_numpy(y[batch]).long()

            data = self.forward(batch_x)
            data.reverse()
            data[-1] = self.softmax(data[-1])
            data.insert(0, batch_x)
            data.append(self.one_hot(batch_y, gpu))

            k_list = [self.kernel_mat(i, n_n) for i in data]
            e_list = [self.entropy(i, n_n, alpha, sigma) for i in k_list]
            j_XT =  [self.j_entropy(k_list[0], k_i, n_n, alpha) for k_i in k_list[1:-1]]
            j_TY =  [self.j_entropy(k_i, k_list[-1], n_n, alpha) for k_i in k_list[1:-1]]

            for idx, val in enumerate(e_list[1:-1]):
                MI_temp.append([e_list[0].cpu().data.numpy()+val.cpu().data.numpy()-j_XT[idx].cpu().data.numpy(),
                           e_list[-1].cpu().data.numpy()+val.cpu().data.numpy()-j_TY[idx].cpu().data.numpy()])
            MI.append(MI_temp)
        return np.array(MI).mean(0)

    def one_hot(self, y, gpu):

        try:
            y = th.from_numpy(y)
        except TypeError:
            None

        y_1d = y
        if gpu:
            y_hot = th.zeros((y.size(0), th.max(y).int()+1)).cuda()
        else:
            y_hot = th.zeros((y.size(0), th.max(y).int()+1))

        for i in range(y.size(0)):
            y_hot[i, y_1d[i].int()] = 1

        return y_hot

    def make_batches(self, N, batch_size):

        idx = random.sample(range(0, N), N)

        for i in range(0, N, batch_size):
            yield idx[i:i+batch_size]