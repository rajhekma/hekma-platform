package com.hekma.identity.repository;

import com.hekma.identity.domain.UserCustomRoleEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.UUID;

@Repository
public interface UserCustomRoleRepository extends JpaRepository<UserCustomRoleEntity, UUID> {

    List<UserCustomRoleEntity> findByUserId(UUID userId);

    List<UserCustomRoleEntity> findByCustomRoleId(UUID customRoleId);

    @Query("SELECT COUNT(ucr) FROM UserCustomRoleEntity ucr " +
           "WHERE ucr.customRole.id = :customRoleId AND ucr.user.isActive = true AND ucr.user.isDeleted = false")
    long countActiveUsersByCustomRoleId(@Param("customRoleId") UUID customRoleId);

    void deleteByUserId(UUID userId);

    void deleteByUserIdAndCustomRoleId(UUID userId, UUID customRoleId);
}
