#include <iostream>

extern "C" {
  void mysubroutine1(const int& a, int &b); // implemented in Fortran
  int myfunction1(const int& a, int &b);    // implemented in Fortan
  
  void mysubroutine2(const int& a, int &b) { // called from Fortran
    mysubroutine1(a,b);
    std::cout << "C++ code: mysubroutine2: value of 'b' [post]: "<<b<<std::endl;
  }
  int myfunction2(const int& a, int &b) { // called from Fortran
    int result = myfunction1(a,b);
    std::cout << "C++ code: mysubroutine2: value of 'b' [post]: "<<b<<std::endl;
    return result;
  }
}