[TOC]

# CPython 垃圾回收

> Author: `crayon`
>
> Ref: [CPython-Internals-GC](https://github.com/zpoint/CPython-Internals/blob/master/Interpreter/gc/gc_cn.md)
>
> Date: `2020/08/29`



## CPython中的垃圾回收机制

### 引用计数机制

> `Include/object.h`
>
> 在计算机科学中, 引用计数是计算机编程语言中的一种**内存管理技术**，是指将资源（可以是对象、内存或磁盘空间等等）的被引用次数保存起来，**当被引用次数变为零时就将其释放**的过程。使用引用计数技术可以实现自动资源管理的目的。同时引用计数还可以指使用引用计数技术回收未使用资源的垃圾回收算法。—— 维基百科

* 创建一个对象并在堆上申请内存时，对象引用计数为1（堆初始化过程）
* 其他对象需要持有该对象时，引用计数+1
* 释放（不需要）一个对象时，例如覆盖值操作，引用计数-1
* 对象引用计数为0，对象进入垃圾回收阶段，回收内存

### 分代回收机制

> `Modules/gcmodule.c`

分代回收机制是一种“combine”机制，包含清理方法及回收策略：

* 分代回收策略
* 标记清除
* ...



## 引用计数法

### 获取引用计数

在CPython中的`/Include/object.h`，`PyObject` 中的`ob_refcnt`表示引用计数，获取方式如下：

```c
static inline Py_ssize_t _Py_REFCNT(const PyObject *ob) {
    return ob->ob_refcnt;
}
```

在Python中可以通过`sys.getrefcount(obj)`获取引用计数

```python
import sys
a = 1
sys.getrefcount(a)
>>> 88
```

### 举个栗子

声明一个名为`s`的变量并初始化值`hello world`，并通过` sys.getrefcount(s)`获取引用计数

```python
s = "hello world"

>>> id(s)
4346803024
>>> sys.getrefcount(s)
2 # 一个来自变量 s, 一个来自 sys.getrefcount 的参数
```

![](./images/refcount1.png)

引用计数为`2`：

*  赋值操作：`s`占有一个计数
* 参数传入：`sys.getrefcount` 的参数占用`hello world`的一个计数

`id(s)`也是传入参数，为何没有计数？

* 变量作用域，在`id(s)`方法生命周期内`hello world`字符串对象的引用计数+1，当返回时参数`s`销毁被回收，引用计数-1
* 进入`sys.getrefcount`，`return ob->ob_refcnt;`时尚且在函数域内，引用占有1



把`s`赋值给`s2`

```python
>>> s2 = s
>>> id(s2)
4321629008 # 和 id(s) 的值一样
>>> sys.getrefcount(s)
3 # 多出来的一个来自 s2
```

![](./images/refcount2.png)

### 字节码执行

执行以上Python语句并输出字节码

```shell
$ cat test.py
s = []
s2 = s
del s
$ ./python.exe -m dis test.py
```

输出字节码：

```Python
1         0 BUILD_LIST               0
          2 STORE_NAME               0 (s)

2         4 LOAD_NAME                0 (s)
          6 STORE_NAME               1 (s2)

3         8 DELETE_NAME              0 (s)
         10 LOAD_CONST               0 (None)
         12 RETURN_VALUE
```

Code Line 1：`s = []`

`0 BUILD_LIST` 

* 申请堆空间，创建一个空白新`list`对象，把对象引用计数设为1，并入栈

`2 STORE_NAME` ，执行字节码：

```c
case TARGET(STORE_NAME): {
    PyObject *name = GETITEM(names, oparg); 	// str对象，值为's'（变量名）
    PyObject *v = POP();	//出栈前一个字节码创建的list对象
    PyObject *ns = f->f_locals;	// ns 是 local namespace，存变量k-v
    int err;
    if (ns == NULL) {
        PyErr_Format(PyExc_SystemError,
                     "no locals found when storing %R", name);
        Py_DECREF(v);
        goto error;
    }
    if (PyDict_CheckExact(ns))
    	/* 在这个位置, v 的引用计数 为 1
           PyDict_SetItem 会把 's' 作为键加到 local namespace 中, 值为对象 v
           ns 类型为 字典对象, 这一操作会同时把 's' 和 v 的引用计数都增加 1
       */
        // 设置变量值
        err = PyDict_SetItem(ns, name, v);
        /* 做完上面的操作, v 的引用计数变为了 2 */
    else
        err = PyObject_SetItem(ns, name, v);
    Py_DECREF(v);
    /* Py_DECREF 之后, v 的引用计数变为了 1 */
    if (err != 0)
        goto error;
    DISPATCH();
}
```

* 为什么初始化引用数为1：前面讲过，在堆上申请空间并且赋值之前需要入栈，引用数为1

综上，第一行代码执行完，引用计数为`1`

Code Line2：`s2 = s`

`4 LOAD_NAME`

* 在`local namespace`取出键为`s`的对象，引用计数+1并推到栈中
* 此时新建`list`对象的引用计数为`2`（s，stack）

`6 STORE_NAME`

* 执行`2 STORE_NAME`过程的代码，把`s2`加入`local namespace`，出栈`list`对象，引用数-1（1）
* `list`对象被`s2`引用，+1（2）

综上，第二行代码的赋值操作使得引用计数`1`->`2`

`8 

```C
case TARGET(DELETE_NAME): {
    PyObject *name = GETITEM(names, oparg);		// name 这里为 's'
    PyObject *ns = f->f_locals;		// ns 为 the local namespace
    int err;
    if (ns == NULL) {
        PyErr_Format(PyExc_SystemError,
                     "no locals when deleting %R", name);
        goto error;
    }
    /* 到这里, list 对象的引用计数为 2
       下面的操作会找到键 's' 对应的位置, 把 indices 设置为 DKIX_DUMMY,
       entries 中的 key 和 value 位置都置为空指针, 并把 key 和 value 本身对象引用计数减1
    */
    err = PyObject_DelItem(ns, name);
    /* 到了这里, list 对象的引用计数变为了 1 */
    if (err != 0) {
        format_exc_check_arg(PyExc_NameError,
                             NAME_ERROR_MSG,
                             name);
        goto error;
    }
    DISPATCH();
}
```



### 触发垃圾回收的条件

```C
/* cpython/Include/object.h */
static inline void _Py_DECREF(const char *filename, int lineno,
                              PyObject *op)
{
    _Py_DEC_REFTOTAL;
    if (--op->ob_refcnt != 0) {
#ifdef Py_REF_DEBUG
        if (op->ob_refcnt < 0) {
            _Py_NegativeRefcount(filename, lineno, op);
        }
#endif
    }
    else {
    	/* // _Py_Dealloc 会找到对应类型的 descructor, 并且调用这个 descructor
        destructor dealloc = Py_TYPE(op)->tp_dealloc;
        (*dealloc)(op);
        */
        _Py_Dealloc(op);
    }
}
```



### 引用循环问题

> `DELETE_NAME` 只会清除传入对象的引用
>
> 引用循环问题是指在某些情况下，由于对象相互引用，引用计数无法变为`0`导致的垃圾回收无法触发的现象

#### 互相引用

```python
class A:
    pass

>>> a1 = A()
>>> a2 = A()
>>> a1.other = a2
>>> a2.other = a1
```

此时`a1` `a2`的引用计数都为2

![](./images/ref_each1.png)

```python
>>> del a1
>>> del a2
```

清空`local namespace`的引用，但由于对象自身都有一个来自对方的引用，`a1` `a2`的引用计数只会变成`1`

![](./images/ref_each2.png)



#### 引用自身

```python
>>> a = list()
>>> a.append(a)
>>> a
[[...]]
```

![](./images/ref_cycle1.png)

````python
>>> del a
````

上述语句清除了`a`在`local namespace`的引用，引用计数变为`1`，而`list`自身持有自己的引用无法消除

![](./images/ref_cycle2.png)



## 分代回收机制

> 仅有**引用计数器机制**在引用循环对象增多后无法进行有效回收，导致解释器进程发生**内存泄漏**
>
> - **内存泄漏**（Memory leak）是在[计算机科学](https://zh.wikipedia.org/wiki/计算机科学)中，由于疏忽或错误造成程序未能释放已经不再使用的[内存](https://zh.wikipedia.org/wiki/内存)。内存泄漏并非指内存在物理上的消失，而是应用程序分配某段内存后，由于设计错误，导致在**释放该段内存之前就失去了对该段内存的控制**，从而造成了内存的浪费。——维基百科
>
> **分代回收机制**是用于处理上述无法被回收的引用循环对象，包含**分代回收**，**标记清除**等一系列操作



### 引用管理

> 追踪分配到堆的所有对象

![](./images/track.png)

* `PyGC_Head * generation0`管理一个双向链表，链表中每个节点都由`PyGC_Head`和`PyObject`
* `PyGC_Head`包含`_gc_next`（后继指针）和`_gc_prev`（前驱节点）
* `PyObject`是Python基础对象

举个例子，当执行`a = list()`，CPython会在堆申请空间存放a指向的对象`PyObject* PyListObject`，同时该对象（指针）添加到`generation0`尾部，所以 `generation0` 可以追踪到所有通过解释器从 heap 空间分配的对象



### 分代回收

通过上述方法管理堆分配对象，对于一些服务型应用（Web服务），随着堆分配对象增加，链表会变得很长：），并且在该链表上**总有一些对象长时间存活**，重复探测长链表触发回收是一个浪费性能的操作

提高垃圾回收效率可以从两方面去考虑

* 加快回收效率
* 减少遍历（链表缩短）

**分代回收**就是通过减少遍历，缩短回收链而提出的垃圾回收策略

* CPython对存活对象分**三代**进行管理，新创建的对象会被存储到第一代`generation0` 
* 当一个对象在一次垃圾回收后存活，这个对象就会被移动到相近的下一代
* 代越年轻，里面的对象也就越新，年轻的代会比年长的代**更频繁进行垃圾回收**
* 当准备回收一个代的时候，**比这个代年轻的代都会被合并**，处理**循环引用对象**及其他可被回收（引用计数为0）的对象



#### update_refs（合并）

```python
>>> c = list()
>>> d1 = A()
>>> d2 = A()
>>> d1.other2 = d2
>>> d2.other2 = d1

>>> del a1
>>> del a2
>>> del b
>>> del d1
>>> gc.collect(1)
```

* 假设`a1` `a2` `b`都在第一次垃圾回收中存活，此时他们指向的对象会从`generation0`移动到`generation1`

* 从`local namespace`中移除`a1` `a2` `b` `b1`，回收`generation1`

![](./images/update_ref1.png)

将比`generation1 `低的代与之合并，合并后的代叫做`young`，比`generation1 `年长的代称为`old`，合并后如下:

![](./images/young_old.png)

**update_refs**会把`young`中所有对象的引用计数拷贝到追踪链上的`_gc_prev`位置

* `_gc_prev`最右两个bit位是预留位（`0x1`），拷贝的引用计数会**左移**两位后存储到`_gc_prev`
* 下图`1 / 0x06`表示引用计数值为`1`，`0x06 = 0x1 << 2 +0x10`

![](./images/update_ref2.png)

#### subtract_refs（消除循环引用）

* 遍历`young`中所有对象
* 检查对象引用其他对象的情况，如果引用对象也在`young`中，并且是**可回收对象**，把相应对象复制到`_gc_prev`部分的引用计数**-1**
* 用`tp_traverse`遍历，遍历回调`visit_decref`

上述步骤的目的是消除当前回收代`young`中**对象间引用**，消除完后，`young`中的对象的引用计数都是来自`young`外引用计数。

* 简单说，就是在`young`内**消除对象引用环**

![](./images/subtract_refs.png)

#### move_unreachable

该步骤创建一个名为`unreachable`的链表，遍历回收代`young`，把上一步处理后**引用计数<=0的对象移动到unreachable**

在上述遍历过程中，如果对象**引用计数>0**，对于当前对象引用到的对象：

* 如果对象**复制引用计数<=0**，置为`1`（引用者没有被回收，作为被引用者也不能被回收
* 如果这个对象在`unreachable`中，移动到`young`链表**尾部**，参与下次检查



**1** 回收`local namespace`，该对象用于`Python`程序管理变量，不能被回收，所以所有被它所引用的对象也不能被回收（回收一个对象之前必须通过`del name`清除在`local namespace`的引用），此时`c` `d2`所指向的对象的`_gc_prev`值被设置为`0x06`

![](./images/move_unreachable1.png)

**2** 回收`a1`（指向的对象，`a1`实际上只是一个对象引用，后续用变量名替代指向对象），`a1`复制引用计数<=0，移动至`unreachable`

![](./images/move_unreachable2.png)

**3** `a2`同上

![](./images/move_unreachable3.png)

**4** `b`也一样

![](./images/move_unreachable4.png)

**5** `c`复制引用计数 > 0 (在**1**时由于检测到被`local namespace`引用，所以从`0x2`->`0x6`)，不会被回收，并且`_gc_prev`会被重置（复制引用计数`bit flag`被清除）

![](./images/move_unreachable5.png)

**6** `d1`复制引用计数 <= 0，被移动到`unreachable`

![](./images/move_unreachable6.png)

**7** 回收`d2`，由于`d2`上存在`d1`的引用，并且`d2`复制引用计数 > 0，`d1`在`unreachable`中

![](./images/move_unreachable7.png)

**此时`d1`复制引用计数被重置为`1`，并移动到回收代链表尾部**

![](./images/move_unreachable8.png)

**8** 回收`d1`，复制引用计数 > 0，重置`_gc_prev`

此时回收代链表已经全部遍历完了，在这个过程中放入`unreachable`中的所有对象都是**没有被其他对象引用**的对象，可以真正进入回收流程

回收代链表留下的对象是在**本轮垃圾回收存活**的，这些对象将被移动到**更年长的代**

![](./images/move_unreachable9.png)



### Finalizer

对于自定义`__del__`的对象，在`__del__`的逻辑里增加对其他对象的引用或自身引用（自救），在`Python3.4`之前，这部分对象会被移动到`gc.garbage`中，需要手动调用他们的`__del__`进行回收

在`Python3.4`后，有下述实现解决这个问题

举个例子

```python
class A:
    pass


class B(list):
    def __del__(self):
        # 增加对自身的引用
        a3.append(self)
        print("del of B")

a1 = A()
a2 = A()
a1.other = a2
a2.other = a1

a3 = list()
b = B()
b.append(b)
del a1
del a2
del b
gc.collect()
```

在指向`move_unreachable`后，对象状态如下

![](./images/finalize1.png)

**1** 所有`unreachable`中自定义`__del__`都会在上述阶段后被调用，在`__del__` 调用后：

![](./images/finalize2.png)

**2** 在`unreachable`中执行`update_refs`（复制引用计数），同时`b`的`_gc_prev`字段的第一个bit会被置为1（赋值引用计数为`2`，原有标志占位为`10`，bit置1后变为`11`，加上赋值引用计数，变为`1011->0x0b`），表示`finalizer`已被处理

![](./images/finalize3.png)

**3** 在`unreachable`中执行`subtract_refs`，消除执行`__del__`后，创建**unreachable对象间的互相引用关系**

遍历每个`unreachable`的对象，对于**复制引用计数>0**的对象，挪动到`old`代，这个现象可以称为对象的自救（他救）过程，取决于在`__del__`中，对象创建对某个对象的引用关系，**对于剩余的对象，直接回收**

![](./images/finalize5.png)

可以看出两张图的区别，由于`b`被存活的`a3`所引用，从而从`unreachable`中移动到`old`

注：如果`__del__`被调用过，**_gc_prev**上的第一个bit flag会被设置为`1`，所有一个对象的`__del__`**仅能被调用一次**



### threshold

CPython中一共三代，每一代都对应一个`threshold`

**在进行回收之前**，CPython会从最年老的代到最年轻的代进行检测，如果当前代中对象数量超过**threshold**，垃圾回收就会从这一代开始

```python
>>> gc.get_threshold()
(700, 10, 10) # 默认值
```

手动设置`threshold`

```python
>>> gc.set_threshold(500)
>>> gc.set_threshold(100, 20)
```



#### 触发分代回收

**方法1** 调用`gc.collect()`，缺省情况下直接从**最年老一代**开始回收

```python
import gc
gc.collect()
```



**方法2** 解释器自行触发，从`heap`申请空间创建一个新对象时，检查`generation0`（新创建对象位于新生代）的数量是否超过`threashold`，超过则进行垃圾回收

![](./images/generation_trigger1.png)

#### 回收流程

`collect`流程从**最年老代**向**最年轻代**进行检查

先检查`generation2`，`generation2`对象存活数比`threashold`小，无需进行垃圾回收

![](./images/generation_trigger2.png)

之后检查`generation1`，超过`threashold`，**垃圾回收从`generation1`进行回收，也就是从这一代起包括更新的代都执行垃圾回收流程**

![](./images/generation_trigger3.png)

回收时会将**开始回收代及其之前代**合并，按上面讲的流程进行回收

![](./images/generation_trigger4.png)

## 总结

`CPython`使用的垃圾回收算法是**非并发的**，非并发会带来的时**复制引用计数和实际对象计数不匹配的问题**，这也强调了全局锁（例如gil）的重要性，全局锁可以在**track(引用管理)**、**分代回收**、**标记清除**等过程中保护这些变量